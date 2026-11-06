"""Detect changes to approved data and issued files before use."""

import hashlib
import hmac
import json
from pathlib import Path
from django.conf import settings
from django.utils.crypto import salted_hmac


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(version):
    requirements = []
    for item in version.required_departments.select_related("seal_version").order_by(
        "department_id"
    ):
        if not hmac.compare_digest(
            file_digest(item.seal_version.image.path), item.seal_version.sha256
        ):
            raise ValueError("公章文件完整性校验失败，已阻止审批和签发")
        requirements.append(
            {
                "department": item.department_id,
                "seal_version": item.seal_version_id,
                "sha256": item.seal_version.sha256,
            }
        )
    payload = {
        "id": version.pk,
        "batch": version.batch_id,
        "number": version.number,
        "template_version": version.template_version_id,
        "snapshot": version.snapshot,
        "output_formats": version.output_formats,
        "submitted_by": version.submitted_by_id,
        "requirements": requirements,
        "awards": list(
            version.awards.order_by("source_row").values(
                "source_row",
                "members",
                "award_name",
                "team_name",
                "work_name",
                "category",
                "teachers",
                "note",
                "last_edited_by_id",
            )
        ),
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return salted_hmac(
        "awardcollection.approved-version.v1",
        serialized,
        secret=getattr(settings, "INTEGRITY_KEY", settings.SECRET_KEY),
        algorithm="sha256",
    ).hexdigest()


def freeze(version):
    version.integrity_hmac = digest(version)
    version.save(update_fields=["integrity_hmac", "updated_at"])


def verify(version):
    if not version.integrity_hmac or not hmac.compare_digest(
        version.integrity_hmac, digest(version)
    ):
        raise ValueError("审批数据完整性校验失败，已阻止操作，请检查审计记录")
