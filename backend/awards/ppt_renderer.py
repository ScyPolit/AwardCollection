"""Render the actual pinned PPTist slide in isolated Chromium, then sign its PDF."""

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
from functools import lru_cache
from fontTools.ttLib import TTFont
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, unquote
from django.conf import settings
from .fonts import font_file, resolved_font_files
from .presentation import presentation_fonts

_local = threading.local()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="certificate-render")


@lru_cache(maxsize=32)
def coverage(path, modified):
    with TTFont(path, lazy=True) as source:
        return sorted((source.getBestCmap() or {}).keys())


class BrowserRenderer:
    def __init__(self):
        from playwright.sync_api import sync_playwright

        self.runtime = sync_playwright().start()
        executable = (
            os.getenv("CHROMIUM_EXECUTABLE_PATH")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
        )
        if not executable and os.name == "nt":
            candidate = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
            if candidate.exists():
                executable = str(candidate)
        self.browser = self.runtime.chromium.launch(
            headless=True,
            executable_path=executable,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-extensions",
            ],
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.url = os.getenv("PPT_RENDER_URL", "http://web:8080/ppt-editor/render.html")
        self.origin = urlparse(self.url)
        self.files = {}
        self.key = None
        self.context.route("**/*", self.route)

    def route(self, route):
        parsed = urlparse(route.request.url)
        if parsed.hostname == "award-fonts.invalid":
            font_id = unquote(parsed.path).removeprefix("/").removesuffix(".ttf")
            path = self.files.get(font_id)
            if path:
                route.fulfill(
                    path=str(path),
                    content_type="font/ttf",
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=3600",
                    },
                )
                return
        if (
            (parsed.scheme, parsed.netloc) == (self.origin.scheme, self.origin.netloc)
            and parsed.path.startswith("/ppt-editor/")
            and route.request.method == "GET"
        ):
            route.continue_()
            return
        route.abort("blockedbyclient")

    def prepare(self, template, seals):
        self.files = {
            font_id: font_file(font_id) for font_id in presentation_fonts(template)
        }
        seal_images = []
        for seal in seals or []:
            seal_images.append(
                {
                    "department_id": seal["department_id"],
                    "src": "data:image/png;base64,"
                    + base64.b64encode(Path(seal["image"]).read_bytes()).decode(),
                }
            )
        payload = {
            "canvas": template,
            "seals": seal_images,
            "fonts": [
                {
                    "id": font_id,
                    "family": "AC_" + font_id.replace("-", "_"),
                    "url": f"http://award-fonts.invalid/{font_id}.ttf",
                    "coverage": coverage(
                        str(self.files[font_id]), self.files[font_id].stat().st_mtime_ns
                    ),
                }
                for font_id in self.files
            ],
        }
        key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if self.key == key:
            return
        width = template["page"]["width"]
        height = template["page"]["height"]
        self.page.set_viewport_size(
            {"width": round(width * 4 / 3), "height": round(height * 4 / 3)}
        )
        if not self.page.url.startswith(self.url):
            self.page.goto(self.url, wait_until="domcontentloaded", timeout=45000)
            self.page.wait_for_function(
                '()=>typeof window.certLoad === "function"', timeout=45000
            )
        self.page.evaluate("payload=>window.certLoad(payload)", payload)
        self.key = key

    def render(self, template, seals, values, output):
        self.prepare(template, seals)
        self.page.evaluate("values=>window.certFill(values)", values)
        pdf = self.page.pdf(
            width=f"{template['page']['width']/72}in",
            height=f"{template['page']['height']/72}in",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            prefer_css_page_size=True,
        )
        if hasattr(output, "write"):
            output.write(pdf)
        else:
            Path(output).write_bytes(pdf)

    def preflight(self, template, seals, rows):
        self.prepare(template, seals)
        return self.page.evaluate("rows=>window.certPreflight(rows)", rows)

    def close(self):
        try:
            self.browser.close()
            self.runtime.stop()
        except Exception:
            pass


def _renderer():
    instance = getattr(_local, "renderer", None)
    if instance is None:
        instance = BrowserRenderer()
        _local.renderer = instance
    return instance


class RendererProxy:
    def invoke(self, method, template, seals, *args):
        files = {
            font_id: str(font_file(font_id)) for font_id in presentation_fonts(template)
        }

        def run():
            with resolved_font_files(files):
                try:
                    return getattr(_renderer(), method)(template, seals, *args)
                except Exception as exc:
                    instance = getattr(_local, "renderer", None)
                    if instance:
                        instance.close()
                        _local.renderer = None
                    raise ValueError(str(exc).splitlines()[0][:1000]) from exc

        return _executor.submit(run).result(timeout=120)

    def render(self, template, seals, values, output):
        return self.invoke("render", template, seals, values, output)

    def preflight(self, template, seals, rows):
        return self.invoke("preflight", template, seals, rows)


def renderer():
    return RendererProxy()


def release_renderer():
    def close():
        instance = getattr(_local, "renderer", None)
        if instance:
            instance.close()
            _local.renderer = None
    _executor.submit(close).result(timeout=15)


def award_values(award, number):
    return {
        "number": number,
        "members": "、".join(award.members),
        "team_name": award.team_name or "、".join(award.members),
        "award_name": award.award_name,
        "work_name": getattr(award, "work_name", ""),
        "category": getattr(award, "category", ""),
        "teachers": "、".join(getattr(award, "teachers", [])),
        "competition_name": getattr(award, "competition_name", ""),
        "issue_date": getattr(award, "issue_date", ""),
    }
