"""Bounded, local-only template imports. Office conversion runs in a separate container."""

import base64
import io
import json
import os
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image

MAX_FILE = 16 * 1024 * 1024


def check_office_archive(content, nested=False):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > (500 if nested else 4000)
                or sum(i.file_size for i in entries)
                > (8 if nested else 100) * 1024 * 1024
            ):
                raise ValueError("Office文件解压后过大")
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts or entry.flag_bits & 1:
                    raise ValueError("Office文件路径或加密格式无效")
                name = entry.filename.lower()
                if not entry.is_dir() and any(
                    token in name for token in ("vbaproject", "activex/")
                ):
                    raise ValueError("不接受宏或ActiveX，请另存为普通PPTX")
                if not entry.is_dir() and "embeddings/" in name:
                    if nested or not name.endswith(".xlsx"):
                        raise ValueError("不接受嵌入程序或OLE对象")
                    check_office_archive(archive.read(entry), nested=True)
                if name.endswith((".xml", ".rels")):
                    data = archive.read(entry)
                    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
                        raise ValueError("Office XML包含不安全实体")
                    if name.endswith(".rels"):
                        root = ET.fromstring(data)
                        for node in root:
                            if node.attrib.get("TargetMode", "").lower() == "external":
                                raise ValueError("文件含外部链接，请删除外部链接后导入")
    except (zipfile.BadZipFile, ET.ParseError, RuntimeError) as exc:
        raise ValueError("Office文件损坏或格式不正确") from exc


def import_file(uploaded):
    content = uploaded.read(MAX_FILE + 1)
    if len(content) > MAX_FILE:
        raise ValueError("导入文件不能超过16MB")
    suffix = Path(uploaded.name).suffix.lower()
    if suffix in {".ppt", ".odp"}:
        if suffix == ".ppt" and not content.startswith(
            bytes.fromhex("D0CF11E0A1B11AE1")
        ):
            raise ValueError("旧版PPT文件头无效")
        if suffix == ".odp":
            check_office_archive(content)
        request = urllib.request.Request(
            os.getenv("OFFICE_CONVERTER_URL", "http://converter:8090")
            + f"/convert?format={suffix[1:]}",
            data=content,
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=75) as response:
                content = response.read(MAX_FILE + 1)
        except Exception as exc:
            raise ValueError("Office转换失败或超时，请另存为PPTX后导入") from exc
        suffix = ".pptx"
    if suffix == ".pptx":
        if len(content) > MAX_FILE:
            raise ValueError("转换后的文件过大")
        check_office_archive(content)
        return {
            "filename": "template.pptx",
            "content": base64.b64encode(content).decode(),
        }
    if suffix in {".json", ".pptist"}:
        if suffix == ".json":
            try:
                value = json.loads(content)
                from .presentation import validate_presentation

                if value.get("engine") == "pptist":
                    return {"canvas": validate_presentation(value)}
                if not isinstance(value.get("slides"), list):
                    raise ValueError("JSON需要包含PPTist页面数据")
            except (UnicodeError, json.JSONDecodeError, AttributeError) as exc:
                raise ValueError("JSON文件无效") from exc
        return {
            "filename": "template" + suffix,
            "content": base64.b64encode(content).decode(),
        }
    images = []
    sizes = []
    if suffix == ".pdf":
        import pymupdf as fitz

        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                if document.is_encrypted or not 1 <= len(document) <= 30:
                    raise ValueError("PDF需要1～30页且不可加密")
                if (
                    sum(p.rect.width * p.rect.height for p in document)
                    > 30 * 1200 * 1200
                ):
                    raise ValueError("PDF页面过大")
                for page in document:
                    if (
                        min(page.rect.width, page.rect.height) < 100
                        or max(page.rect.width, page.rect.height) > 2400
                    ):
                        raise ValueError("PDF页面尺寸不支持")
                    sizes.append((page.rect.width, page.rect.height))
                    images.append(
                        page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).tobytes("png")
                    )
        except (RuntimeError, ValueError) as exc:
            raise ValueError("PDF无法读取：" + str(exc)) from exc
    elif suffix in {".png", ".jpg", ".jpeg"}:
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > 20_000_000:
                    raise ValueError("背景图片不能超过2000万像素")
                image.load()
                width = min(1200, image.width)
                height = width * image.height / image.width
                if not 100 <= height <= 2400:
                    raise ValueError("图片比例不支持")
                out = io.BytesIO()
                image.convert("RGB").save(out, "PNG")
                images = [out.getvalue()]
                sizes = [(width, height)]
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError("图片无法读取") from exc
    else:
        raise ValueError("支持 PPT、PPTX、ODP、PDF、PNG/JPG、PPTist及JSON")
    width, height = sizes[0]
    slides = [
        {
            "id": f"import-{i}",
            "elements": [],
            "background": {
                "type": "image",
                "image": {
                    "src": "data:image/png;base64," + base64.b64encode(image).decode(),
                    "size": "cover",
                },
            },
        }
        for i, image in enumerate(images)
    ]
    from .presentation import validate_presentation

    return {
        "canvas": validate_presentation(
            {
                "engine": "pptist",
                "page": {"width": width, "height": height},
                "slideIndex": 0,
                "presentation": {
                    "title": "导入模板",
                    "viewportSize": width,
                    "viewportRatio": height / width,
                    "theme": {
                        "fontName": "AC_hei",
                        "fontColor": "#222",
                        "backgroundColor": "#fff",
                        "themeColors": ["#409eff"],
                    },
                    "slides": slides,
                },
            }
        )
    }
