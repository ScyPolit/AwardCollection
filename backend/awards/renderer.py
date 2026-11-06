import hashlib
import base64
import io
import os
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace

import fitz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.conf import settings
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec
from pyhanko.sign.signers import PdfSignatureMetadata, PdfSigner
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from .fonts import layout_text


KEY_PASSWORD = os.getenv("SIGNING_KEY_PASSWORD", "local-test-only-change-before-deploy").encode()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def font_path():
    candidates = [
        os.getenv("CERTIFICATE_FONT", ""),
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/Deng.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError("未找到随部署提供的中文字体")


def wrap_text(text, font_name, size, width):
    lines, current = [], ""
    for character in text:
        candidate = current + character
        if current and pdfmetrics.stringWidth(candidate, font_name, size) > width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def fit_text(text, font_name, width, height, maximum, minimum):
    for size in range(maximum, minimum - 1, -1):
        lines = wrap_text(text, font_name, size, width)
        leading = size * 1.35
        if len(lines) * leading <= height:
            return size, leading, lines
    raise ValueError("文本在最小字号下仍然溢出")


def draw_fitted(c, text, field, x, y, width, height, maximum, minimum):
    try:
        size, leading, lines = fit_text(text, "CertificateCJK", width, height, maximum, minimum)
    except ValueError as exc:
        raise ValueError(f"{field}：{exc}") from exc
    cursor = y + height - leading
    c.setFont("CertificateCJK", size)
    for line in lines:
        c.drawCentredString(x + width / 2, cursor, line)
        cursor -= leading


def department_pfx(department):
    key_dir = Path(settings.MEDIA_ROOT) / "protected" / "signing-keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    path = key_dir / f"department-{department.id}.p12"
    if path.exists():
        return path
    lock = path.with_suffix(".lock")
    acquired = False
    for _ in range(100):
        try:
            lock.mkdir()
            acquired = True
            break
        except FileExistsError:
            if path.exists():
                return path
            time.sleep(0.1)
    if not acquired:
        raise RuntimeError(f"无法取得部门 {department.id} 的签名密钥创建锁")
    try:
        if path.exists():
            return path
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AwardCollection TEST ONLY"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{department.name} 测试签名"),
        ])
        now = datetime.now(dt_timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
        data = pkcs12.serialize_key_and_certificates(
            f"dept-{department.id}".encode(), key, cert, None,
            serialization.BestAvailableEncryption(KEY_PASSWORD),
        )
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        lock.rmdir()
    return path


def _data_image(value):
    if not value:
        return None
    if value.startswith("data:"):
        _, encoded = value.split(",", 1)
        return ImageReader(io.BytesIO(base64.b64decode(encoded)))
    path = Path(value)
    return ImageReader(str(path)) if path.exists() else None


def _field_value(award, field, number):
    values = {
        "number": number,
        "members": "、".join(award.members),
        "team_name": award.team_name or "、".join(award.members),
        "award_name": award.award_name,
        "work_name": getattr(award, "work_name", ""),
        "category": getattr(award, "category", ""),
        "teachers": "、".join(getattr(award, "teachers", [])),
    }
    return values.get(field, "")


def _draw_text_layer(c, layer, award, number, page_height):
    text = layer.get("text") if layer.get("field") == "static" else _field_value(award, layer.get("field"), number)
    if not text:
        return
    x = float(layer.get("x", 80)); top = float(layer.get("y", 80))
    try:
        layout = layout_text(str(text), layer)
    except ValueError as exc:
        raise ValueError(f"{layer.get('field', '文本')}：{exc}") from exc
    c.setFillColor(layer.get("color", "#1f2937"))
    for line in layout["lines"]:
        for run in line["runs"]:
            c.setFont(run["fontName"], layout["fontSize"])
            c.drawString(x + run["x"], page_height - top - line["baseline"], run["text"])


def render_unsigned(award, number, output, template=None, seals=None):
    font = font_path()
    pdfmetrics.registerFont(TTFont("CertificateCJK", str(font), subfontIndex=0))
    template = template or {}
    page_config = template.get("page", {})
    page = (float(page_config.get("width", 842)), float(page_config.get("height", 595)))
    target = output if hasattr(output, "write") else str(output)
    c = canvas.Canvas(target, pagesize=page, pageCompression=1)
    background = _data_image(template.get("background"))
    if background:
        c.drawImage(background, 0, 0, width=page[0], height=page[1], preserveAspectRatio=False, mask="auto")
    layers = template.get("layers") or []
    if not layers:
        layers = [
            {"type": "text", "field": "static", "text": template.get("title", "获 奖 证 书"), "x": 110, "y": 105, "width": 622, "height": 60, "fontSize": template.get("size", 34), "color": template.get("color", "#1f2937")},
            {"type": "text", "field": "team_name", "x": 110, "y": 190, "width": 622, "height": 65, "fontSize": 22, "minFontSize": 11},
            {"type": "text", "field": "award_name", "x": 110, "y": 280, "width": 622, "height": 50, "fontSize": 18, "minFontSize": 10},
            {"type": "text", "field": "work_name", "x": 110, "y": 350, "width": 622, "height": 62, "fontSize": 18, "minFontSize": 10},
        ]
        if template.get("number", template.get("showNumber", True)):
            layers.append({"type": "text", "field": "number", "x": 72, "y": 500, "width": 300, "height": 25, "fontSize": 11, "align": "left"})
    seal_map = {str(item["department_id"]): item for item in (seals or [])}
    for layer in layers:
        if layer.get("type") == "text":
            _draw_text_layer(c, layer, award, number, page[1])
        elif layer.get("type") == "seal":
            item = seal_map.get(str(layer.get("department")))
            image = _data_image(item.get("image") if item else None)
            if image:
                size = float(layer.get("size", 100)); x = float(layer.get("x", 600)); top = float(layer.get("y", 420))
                c.drawImage(image, x, page[1] - top - size, width=size, height=size, preserveAspectRatio=True, mask="auto")
    if template.get("watermark", template.get("showWatermark", False)):
        c.saveState(); c.setFillColorRGB(0.75, 0.75, 0.75); c.setFont("CertificateCJK", 9)
        c.drawRightString(page[0] - 60, 35, number); c.restoreState()
    c.save()


def append_signature(source, destination, department, index):
    signer = signers.SimpleSigner.load_pkcs12(str(department_pfx(department)), passphrase=KEY_PASSWORD)
    field = f"Department_{department.id}_Signature"
    with open(source, "rb") as inf, open(destination, "wb") as outf:
        writer = IncrementalPdfFileWriter(inf)
        spec = SigFieldSpec(sig_field_name=field, on_page=0, box=(0, 0, 0, 0))
        metadata = PdfSignatureMetadata(field_name=field, md_algorithm="sha256", reason="测试专用电子证书部门会签", location="校内测试环境")
        PdfSigner(metadata, signer=signer, new_field_spec=spec).sign_pdf(writer, output=outf)


def render_certificate(award, number, departments=None, template=None, seals=None, output_root=None, make_image=True):
    root = Path(output_root) if output_root else Path(settings.MEDIA_ROOT) / "protected" / "certificates" / str(datetime.now().year)
    root.mkdir(parents=True, exist_ok=True)
    base = root / number
    unsigned = base.with_suffix(".unsigned.pdf")
    render_unsigned(award, number, unsigned, template=template, seals=seals)
    current = unsigned
    departments = departments or [
        requirement.department
        for requirement in award.version.required_departments.select_related("department").order_by("department_id")
    ]
    for index, department in enumerate(departments):
        signed = base.with_suffix(f".signed-{index + 1}.pdf")
        append_signature(current, signed, department, index)
        if current != unsigned and current.exists():
            current.unlink()
        current = signed
    final_pdf = base.with_suffix(".pdf")
    current.replace(final_pdf)
    unsigned.unlink(missing_ok=True)
    image = None
    if make_image:
        document = fitz.open(final_pdf)
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = base.with_suffix(".png")
        pixmap.save(image)
        document.close()
    return final_pdf, image, sha256(final_pdf)


def render_certificate_payload(payload, number, department_payloads, template=None, seals=None, output_root=None, make_image=True):
    award = SimpleNamespace(**payload)
    departments = [SimpleNamespace(**item) for item in department_payloads]
    return render_certificate(award, number, departments, template, seals, output_root, make_image)
