import time
import os
import shutil
from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction, connections
from django.utils import timezone
from awards.models import AwardBatch, Certificate, DepartmentMembership, GenerationTask, Notification
from awards.renderer import render_certificate_payload
from awards.services import allocate_number, claim_task
from awards.fonts import font_file


def process_task(task):
    lease_token = task.lease_token
    requirements = list(task.version.required_departments.select_related("department", "seal_version__seal").order_by("department_id"))
    for requirement in requirements:
        if not requirement.seal_version.seal.active:
            raise RuntimeError(f"{requirement.department.name} 的选定公章已停用")
    departments = [{"id": item.department.id, "name": item.department.name} for item in requirements]
    seals = [{
        "department_id": item.department_id,
        "seal_version_id": item.seal_version_id,
        "image": item.seal_version.image.path,
    } for item in requirements]
    template = task.version.snapshot.get("template") or task.version.template_version.canvas
    font_ids = {'hei'} | {layer.get('fontFamily') or 'hei' for layer in template.get('layers', []) if layer.get('type') == 'text'}
    # Resolve uploaded fonts before forking; render children must not use ORM
    # or inherit a live PostgreSQL connection from the parent.
    font_files = {font_id: str(font_file(font_id)) for font_id in font_ids}
    make_image = "png" in task.version.output_formats
    attempt_root = Path(settings.MEDIA_ROOT) / "temporary" / "generation" / str(task.id) / str(lease_token)
    attempt_root.mkdir(parents=True, exist_ok=True)
    pending = []
    for award in task.version.awards.order_by("source_row"):
        with transaction.atomic():
            certificate = Certificate.objects.select_for_update().filter(award=award).first()
            if certificate is None:
                certificate = Certificate.objects.create(award=award, number=allocate_number())
        if certificate.pdf and certificate.pdf.storage.exists(certificate.pdf.name):
            continue
        pending.append((award, certificate))

    concurrency = max(1, min(int(os.getenv("RENDER_CONCURRENCY", "4")), 8))

    def payload(item):
        award, certificate = item
        return ({
            "team_name": award.team_name,
            "members": award.members,
            "award_name": award.award_name,
            "work_name": award.work_name,
            "category": award.category,
            "teachers": award.teachers,
        }, certificate.number, departments, template, seals, str(attempt_root), make_image, font_files, certificate.id)

    jobs = [payload(item) for item in pending]
    connections.close_all()
    with ProcessPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(render_certificate_payload, *job[:-1]): job
            for job in jobs
        }
        while futures:
            done, _ = wait(futures, timeout=30, return_when=FIRST_COMPLETED)
            with transaction.atomic():
                current = GenerationTask.objects.select_for_update().get(pk=task.pk)
                if current.lease_token != lease_token or current.status != GenerationTask.Status.RUNNING:
                    raise RuntimeError("任务租约已失效，旧 worker 停止写入")
                current.lease_expires_at = timezone.now() + timedelta(minutes=10)
                current.save(update_fields=["lease_expires_at", "updated_at"])
            for future in done:
                job = futures.pop(future)
                pdf, image, digest = future.result()
                with transaction.atomic():
                    current = GenerationTask.objects.select_for_update().get(pk=task.pk)
                    if current.lease_token != lease_token or current.status != GenerationTask.Status.RUNNING:
                        raise RuntimeError("任务租约已失效，旧 worker 停止写入")
                    certificate = Certificate.objects.select_for_update().get(pk=job[-1])
                    final_root = Path(settings.MEDIA_ROOT) / "protected" / "certificates" / str(timezone.localdate().year)
                    final_root.mkdir(parents=True, exist_ok=True)
                    final_pdf = final_root / f"{certificate.number}.pdf"
                    os.replace(pdf, final_pdf)
                    certificate.pdf.name = str(final_pdf.relative_to(settings.MEDIA_ROOT)).replace("\\", "/")
                    if image:
                        final_image = final_root / f"{certificate.number}.png"
                        os.replace(image, final_image)
                        certificate.image.name = str(final_image.relative_to(settings.MEDIA_ROOT)).replace("\\", "/")
                    else:
                        certificate.image = ""
                    certificate.pdf_sha256 = digest
                    certificate.save(update_fields=["pdf", "image", "pdf_sha256", "updated_at"])
                    current.processed = Certificate.objects.filter(award__version=current.version).exclude(pdf="").count()
                    current.lease_expires_at = timezone.now() + timedelta(minutes=10)
                    current.save(update_fields=["processed", "lease_expires_at", "updated_at"])
    with transaction.atomic():
        current = GenerationTask.objects.select_for_update().get(pk=task.pk)
        if current.lease_token != lease_token:
            raise RuntimeError("任务租约已由其他 worker 接管")
        ready = Certificate.objects.filter(award__version=current.version).exclude(pdf="").count()
        if ready != current.total:
            raise RuntimeError(f"仅生成 {ready}/{current.total} 份证书，拒绝发布")
        published_at = timezone.now()
        Certificate.objects.filter(award__version=current.version, published_at__isnull=True).update(published_at=published_at)
        current.processed = ready
        current.status = GenerationTask.Status.DONE
        current.error = ""
        current.lease_expires_at = None
        current.save(update_fields=["status", "error", "processed", "lease_expires_at", "updated_at"])
        current.version.batch.status = AwardBatch.Status.ISSUED
        current.version.batch.save(update_fields=["status", "updated_at"])
        competition = current.version.batch.competition
        recipients = set(competition.collaborators.values_list("id", flat=True))
        recipients.update(DepartmentMembership.objects.filter(
            department__competitions=competition, role=DepartmentMembership.Role.ADMIN, active=True,
        ).values_list("user_id", flat=True))
        Notification.objects.bulk_create([
            Notification(user_id=user_id, title="证书签发完成", body=f"批次“{current.version.batch.name}”的 {ready} 份证书已全部发布")
            for user_id in recipients
        ])
    shutil.rmtree(attempt_root, ignore_errors=True)
    return current


class Command(BaseCommand):
    help = "Run the persistent certificate generation worker"

    def handle(self, *args, **options):
        self.stdout.write("worker started")
        while True:
            task = claim_task()
            if task is None:
                if options["once"]:
                    return
                time.sleep(2)
                continue
            try:
                process_task(task)
            except Exception as exc:
                GenerationTask.objects.filter(pk=task.pk, lease_token=task.lease_token).update(
                    status=GenerationTask.Status.FAILED, error=str(exc)
                )
            if options["once"]:
                return

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one queued task and exit")
