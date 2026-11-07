#!/usr/bin/env python3
"""Deploy an immutable public Git revision without replacing existing data volumes."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request

BASE = Path("/opt/awardcollection-v1-test")
PROJECT = BASE / "app"
PROJECT_NAME = "awardcollection-v1-test"
SERVICES = ("api", "worker", "web", "converter")


def run(args, *, capture=False, timeout=1800):
    return subprocess.run(
        args,
        cwd=PROJECT,
        text=True,
        capture_output=capture,
        check=True,
        timeout=timeout,
    )


def compose(*args, capture=False, timeout=1800):
    return run(
        ["docker", "compose", "-p", PROJECT_NAME, *args],
        capture=capture,
        timeout=timeout,
    )


def snapshot():
    code = """import json,hashlib
from pathlib import Path
from awards.models import Certificate,TemplateVersion,GenerationTask
if GenerationTask.objects.filter(status__in=['queued','running']).exists():raise RuntimeError('Wait for active generation tasks before deploying')
q=Certificate.objects.order_by('pk')
ids=list(q.values_list('pk',flat=True))
sample=[]
for pk in sorted(set([ids[0],ids[len(ids)//2],ids[-1]])) if ids else []:
 c=q.get(pk=pk)
 sample.append([c.number,c.pdf_sha256,hashlib.sha256(Path(c.pdf.path).read_bytes()).hexdigest() if c.pdf else ''])
versions=[[v.pk,hashlib.sha256(json.dumps(v.canvas,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()] for v in TemplateVersion.objects.order_by('pk')]
print('DEPLOY_SNAPSHOT='+json.dumps({'certificates':q.count(),'published':q.filter(published_at__isnull=False).count(),'sample':sample,'template_versions':versions}))
"""
    result = compose(
        "exec",
        "-T",
        "api",
        "python",
        "manage.py",
        "shell",
        "-c",
        code,
        capture=True,
        timeout=60,
    )
    line = next(
        x for x in result.stdout.splitlines() if x.startswith("DEPLOY_SNAPSHOT=")
    )
    return json.loads(line.split("=", 1)[1])


def set_env(text, values):
    lines = text.splitlines()
    for key, value in values.items():
        lines = [line for line in lines if not line.startswith(key + "=")]
        lines.append(key + "=" + str(value))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("revision")
    parser.add_argument("--archive")
    parser.add_argument("--archive-sha256")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise SystemExit("A full Git commit revision is required")
    if PROJECT.resolve() != PROJECT or not (PROJECT / ".env").is_file():
        raise SystemExit("Expected existing project and private configuration")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    release = BASE / "releases" / (args.revision + "-" + stamp)
    release.mkdir(parents=True, exist_ok=False)
    runtime = PROJECT / "runtime"
    runtime.mkdir(exist_ok=True, mode=0o700)
    status_path = runtime / "release-status.json"
    status = {"revision": args.revision, "stage": "download", "started_at": stamp}

    def progress(stage, **details):
        status.update(stage=stage, **details)
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        print(json.dumps({"stage": stage, **details}), flush=True)

    archive = release / "source.tar.gz"
    if args.archive:
        incoming = Path(args.archive).resolve()
        if not incoming.is_relative_to(BASE / "incoming") or not re.fullmatch(
            r"[0-9a-f]{64}", args.archive_sha256 or ""
        ):
            raise RuntimeError(
                "Uploaded archive needs a trusted SHA256 and incoming directory"
            )
        if hashlib.sha256(incoming.read_bytes()).hexdigest() != args.archive_sha256:
            raise RuntimeError("Uploaded source checksum mismatch")
        shutil.copyfile(incoming, archive)
    else:
        run(
            [
                "curl",
                "--fail",
                "--location",
                "--retry",
                "2",
                "--connect-timeout",
                "15",
                "--max-time",
                "180",
                "-o",
                str(archive),
                "https://codeload.github.com/ScyPolit/AwardCollection/tar.gz/"
                + args.revision,
            ]
        )
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(release, filter="data")
    roots = [p for p in release.iterdir() if p.is_dir()]
    if len(roots) != 1 or not (roots[0] / "compose.yaml").is_file():
        raise RuntimeError("Unexpected release archive layout")
    source = roots[0]
    font_root = source / "backend/font-assets"
    font_cache = BASE / "font-cache"
    for font in json.loads((font_root / "manifest.json").read_text(encoding="utf8")):
        name = font["file"]
        if Path(name).name != name:
            raise RuntimeError("Invalid built-in font path")
        cached = font_cache / name
        if cached.is_file():
            if hashlib.sha256(cached.read_bytes()).hexdigest() != font["sha256"]:
                raise RuntimeError("Cached font checksum mismatch: " + font["id"])
            shutil.copyfile(cached, font_root / name)
    wheel_cache = BASE / "wheel-cache" / "linux-cp312-amd64"
    wheel_manifest = source / "backend/wheel-assets/manifest.json"
    if wheel_cache.is_dir():
        run(
            [
                "python3",
                str(source / "backend/tools/verify_wheel_cache.py"),
                "--root",
                str(wheel_cache),
                "--manifest",
                str(wheel_manifest),
            ],
            capture=True,
            timeout=60,
        )
        target = source / "backend/.offline-wheels"
        target.mkdir(exist_ok=True)
        for item in json.loads(wheel_manifest.read_text())["files"]:
            shutil.copyfile(wheel_cache / item["name"], target / item["name"])
        (target / "READY").write_text(
            hashlib.sha256(wheel_manifest.read_bytes()).hexdigest()
        )
    checkpoint = BASE / "rollback" / stamp
    checkpoint.mkdir(parents=True, mode=0o700)
    old_env = (PROJECT / ".env").read_text()
    old_compose = (PROJECT / "compose.yaml").read_bytes()
    (checkpoint / "compose.yaml").write_bytes(old_compose)
    rollback = {"services": {}}
    for service in SERVICES:
        if service == "converter":
            continue
        image = run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.Image}}",
                PROJECT_NAME + "-" + service + "-1",
            ],
            capture=True,
        ).stdout.strip()
        tag = PROJECT_NAME + "-" + service + ":rollback-" + stamp
        run(["docker", "tag", image, tag])
        rollback["services"][service] = {"image": tag}
    (checkpoint / "images.json").write_text(json.dumps(rollback, indent=2) + "\n")
    before = snapshot()
    (checkpoint / "before.json").write_text(json.dumps(before, indent=2) + "\n")
    (PROJECT / "deploy").mkdir(exist_ok=True)
    for name in ("maintenance.sh", "install-maintenance.sh"):
        shutil.copyfile(source / "deploy" / name, PROJECT / "deploy" / name)
    progress("backup", checkpoint=str(checkpoint))
    try:
        run(["sh", str(PROJECT / "deploy/maintenance.sh"), "backup"], timeout=3600)
    except Exception:
        progress(
            "failed", error="Backup failed before application containers were changed"
        )
        raise
    backup = (runtime / "last-backup-path").read_text().strip()
    (checkpoint / "backup-path").write_text(backup + "\n")
    started_services = False
    try:
        progress("configure", source=str(source), backup=backup)
        (PROJECT / ".env").write_text(
            set_env(
                old_env,
                {
                    "APP_SOURCE_DIR": source,
                    "APP_BUILD_VERSION": args.revision,
                    "DJANGO_DEBUG": "false",
                    "RENDER_CONCURRENCY": "1",
                    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://192.168.31.12:18443",
                },
            )
        )
        os.chmod(PROJECT / ".env", 0o600)
        shutil.copyfile(source / "compose.yaml", PROJECT / "compose.yaml")
        config = json.loads(compose("config", "--format", "json", capture=True).stdout)
        for volume in ("db_data", "media_data", "backup_data"):
            if config["volumes"][volume]["name"] != PROJECT_NAME + "_" + volume:
                raise RuntimeError("Existing volume identity changed")
        progress("build")
        compose("build", *SERVICES, timeout=3600)
        progress("restart")
        started_services = True
        compose("stop", "--timeout", "30", "worker", timeout=60)
        compose("up", "-d", "--no-deps", "api", "converter", timeout=240)
        api_ready = False
        for _ in range(90):
            state = run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    PROJECT_NAME + "-api-1",
                ],
                capture=True,
            ).stdout.strip()
            if state == "healthy":
                api_ready = True
                break
            time.sleep(2)
        if not api_ready:
            raise RuntimeError("API failed startup/migration health check")
        compose(
            "exec",
            "-T",
            "api",
            "python",
            "manage.py",
            "shell",
            "-c",
            "from django.contrib.sessions.models import Session;from awards.models import AuditEvent;Session.objects.all().delete();AuditEvent.objects.create(action='security.sessions_rotated_for_https',object_type='System',object_id='v4')",
            capture=True,
            timeout=30,
        )
        compose("up", "-d", "--no-deps", "worker", "web", timeout=240)
        progress("health")
        healthy = False
        for _ in range(45):
            try:
                result = compose(
                    "exec",
                    "-T",
                    "api",
                    "python",
                    "-c",
                    "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/').read().decode())",
                    capture=True,
                    timeout=15,
                )
                health = json.loads(result.stdout)
                healthy = health.get("version") == args.revision
                if healthy:
                    break
            except Exception:
                pass
            time.sleep(2)
        if not healthy:
            raise RuntimeError("New application version did not become healthy")
        for service in SERVICES:
            actual = run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "org.opencontainers.image.revision"}}',
                    PROJECT_NAME + "-" + service + "-1",
                ],
                capture=True,
            ).stdout.strip()
            if actual != args.revision:
                raise RuntimeError("Image version mismatch for " + service)
        after = snapshot()
        (checkpoint / "after.json").write_text(json.dumps(after, indent=2) + "\n")
        if before != after:
            raise RuntimeError(
                "Existing certificate or template content changed during deployment"
            )
        run(["sh", str(PROJECT / "deploy/install-maintenance.sh")], timeout=60)
        progress(
            "done",
            source=str(source),
            backup=backup,
            existing_content_preserved=True,
            health=health,
        )
    except Exception as exc:
        (PROJECT / ".env").write_text(old_env)
        (PROJECT / "compose.yaml").write_bytes(old_compose)
        if started_services:
            try:
                compose(
                    "-f",
                    "compose.yaml",
                    "-f",
                    str(checkpoint / "images.json"),
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "api",
                    "worker",
                    "web",
                    timeout=240,
                )
            except Exception:
                progress("rollback-failed", error=str(exc))
                raise
        progress("failed", error=str(exc), containers_rolled_back=started_services)
        raise


if __name__ == "__main__":
    main()
