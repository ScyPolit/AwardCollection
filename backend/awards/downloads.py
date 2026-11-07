"""Authorized disk downloads: bounded verification, Nginx transfer and range support."""
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.utils.http import content_disposition_header
from rest_framework.exceptions import APIException, NotFound
from .integrity import file_digest


@lru_cache(maxsize=128)
def verified_digest(path, size, mtime, ctime, inode):
    return file_digest(path)


class IntegrityConflict(APIException):
    status_code = 409
    default_detail = "文件完整性校验失败，下载已阻止"


def disk_response(path, *, digest="", filename=None, content_type="application/octet-stream", inline=False):
    path = Path(path).resolve()
    if not path.is_file():
        raise NotFound("文件不存在，请重新生成或联系管理员")
    stat = path.stat()
    if not digest or verified_digest(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino) != digest:
        raise IntegrityConflict()
    protected = (Path(settings.MEDIA_ROOT) / "protected").resolve()
    if getattr(settings, "USE_ACCEL_DOWNLOAD", False) and path.is_relative_to(protected):
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = "/_protected-downloads/" + quote(path.relative_to(protected).as_posix(), safe="/")
        response["Content-Disposition"] = content_disposition_header(not inline, filename or path.name)
        response["Cache-Control"] = "private, no-store"
        return response
    response = FileResponse(path.open("rb"), as_attachment=not inline, filename=filename or path.name, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    return response
