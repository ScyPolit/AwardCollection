"""Single-request Office converter, unprivileged and without external networking."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import ctypes
from pathlib import Path
import signal
import subprocess
import tempfile
from urllib.parse import urlparse, parse_qs


def deny_outbound():
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x7FFF0000)
    connect = library.seccomp_syscall_resolve_name(b"connect")
    if (
        not context
        or connect < 0
        or library.seccomp_rule_add(context, 0x00050000 | 13, connect, 0) != 0
        or library.seccomp_load(context) != 0
    ):
        raise RuntimeError("Unable to isolate office networking")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        try:
            suffix = parse_qs(urlparse(self.path).query).get("format", [""])[0]
            size = int(self.headers.get("Content-Length", "0"))
            if suffix not in {"ppt", "odp"} or not 0 < size <= 16 * 1024 * 1024:
                raise ValueError("invalid input")
            self.connection.settimeout(20)
            data = self.rfile.read(size)
            if len(data) != size:
                raise ValueError("incomplete upload")
            with tempfile.TemporaryDirectory(prefix="office-") as directory:
                root = Path(directory)
                source = root / ("input." + suffix)
                source.write_bytes(data)
                profile = root / "profile"
                user = profile / "user"
                user.mkdir(parents=True)
                (user / "registrymodifications.xcu").write_text(
                    """<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item><item oor:path="/org.openoffice.Office.Common/Load"><prop oor:name="UpdateLinkMode" oor:op="fuse"><value>0</value></prop></item></oor:items>"""
                )
                process = subprocess.Popen(
                    [
                        "soffice",
                        "-env:UserInstallation=" + profile.as_uri(),
                        "--headless",
                        "--nologo",
                        "--nodefault",
                        "--nofirststartwizard",
                        "--convert-to",
                        "pptx:Impress MS PowerPoint 2007 XML",
                        "--outdir",
                        directory,
                        str(source),
                    ],
                    start_new_session=True,
                    preexec_fn=deny_outbound,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "SAL_USE_VCLPLUGIN": "svp"},
                )
                try:
                    process.communicate(timeout=55)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise
                if process.returncode:
                    raise ValueError("conversion failed")
                content = (root / "input.pptx").read_bytes()
                if len(content) > 16 * 1024 * 1024:
                    raise ValueError("output too large")
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(422)
            self.end_headers()
            self.wfile.write(b"conversion failed")

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
