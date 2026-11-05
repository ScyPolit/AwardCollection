import hashlib
import os
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

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
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    return path


def render_unsigned(award, number, output):
    font = font_path()
    pdfmetrics.registerFont(TTFont("CertificateCJK", str(font), subfontIndex=0))
    page = (842, 595)
    c = canvas.Canvas(str(output), pagesize=page, pageCompression=1)
    c.setStrokeColorRGB(0.18, 0.27, 0.38)
    c.setLineWidth(4)
    c.rect(24, 24, page[0] - 48, page[1] - 48)
    c.setFont("CertificateCJK", 12)
    c.drawCentredString(page[0] / 2, 550, "校赛电子证书系统 | 测试专用")
    c.setFont("CertificateCJK", 34)
    c.drawCentredString(page[0] / 2, 465, "获 奖 证 书")
    team = award.team_name or "、".join(award.members)
    draw_fitted(c, team, "团队名称或成员", 110, 340, 622, 65, 22, 11)
    c.setFont("CertificateCJK", 16)
    c.drawCentredString(page[0] / 2, 315, f"荣获 {award.award_name}")
    if award.work_name:
        draw_fitted(c, award.work_name, "作品名称", 110, 230, 622, 62, 18, 10)
    c.setFont("CertificateCJK", 11)
    c.drawString(72, 75, f"证书编号：{number}")
    c.drawRightString(770, 75, "本文件为系统验收测试产物")
    c.save()


def append_signature(source, destination, department, index):
    signer = signers.SimpleSigner.load_pkcs12(str(department_pfx(department)), passphrase=KEY_PASSWORD)
    x1 = 80 + (index % 3) * 230
    field = f"Department_{department.id}_Signature"
    with open(source, "rb") as inf, open(destination, "wb") as outf:
        writer = IncrementalPdfFileWriter(inf)
        spec = SigFieldSpec(sig_field_name=field, on_page=0, box=(x1, 120, x1 + 190, 170))
        metadata = PdfSignatureMetadata(field_name=field, md_algorithm="sha256", reason="测试专用电子证书部门会签", location="校内测试环境")
        PdfSigner(metadata, signer=signer, new_field_spec=spec).sign_pdf(writer, output=outf)


def render_certificate(award, number):
    root = Path(settings.MEDIA_ROOT) / "protected" / "certificates" / str(datetime.now().year)
    root.mkdir(parents=True, exist_ok=True)
    base = root / number
    unsigned = base.with_suffix(".unsigned.pdf")
    render_unsigned(award, number, unsigned)
    current = unsigned
    requirements = list(award.version.required_departments.select_related("department").order_by("department_id"))
    for index, requirement in enumerate(requirements):
        signed = base.with_suffix(f".signed-{index + 1}.pdf")
        append_signature(current, signed, requirement.department, index)
        if current != unsigned and current.exists():
            current.unlink()
        current = signed
    final_pdf = base.with_suffix(".pdf")
    current.replace(final_pdf)
    unsigned.unlink(missing_ok=True)
    document = fitz.open(final_pdf)
    pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = base.with_suffix(".png")
    pixmap.save(image)
    document.close()
    return final_pdf, image, sha256(final_pdf)
