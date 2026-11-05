import time
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from awards.models import AwardBatch, Certificate, GenerationTask
from awards.renderer import render_certificate_payload
from awards.services import allocate_number, claim_task


def process_task(task):
    lease_token = task.lease_token
    departments = [
        {"id": requirement.department.id, "name": requirement.department.name}
        for requirement in task.version.required_departments.select_related("department").order_by("department_id")
    ]
    pending = []
    for award in task.version.awards.order_by("source_row"):
        with transaction.atomic():
            certificate = Certificate.objects.select_for_update().filter(award=award).first()
            if certificate is None:
                certificate = Certificate.objects.create(award=award, number=allocate_number())
        if certificate.pdf:
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
        }, certificate.number, departments, certificate.id)

    jobs = [payload(item) for item in pending]
    with ProcessPoolExecutor(max_workers=concurrency) as executor:
        results = executor.map(
            render_certificate_payload,
            (job[0] for job in jobs),
            (job[1] for job in jobs),
            (job[2] for job in jobs),
            chunksize=1,
        )
        for job, (pdf, image, digest) in zip(jobs, results):
            certificate = Certificate.objects.get(pk=job[3])
            certificate.pdf.name = str(pdf.relative_to(pdf.parents[3])).replace("\\", "/")
            certificate.image.name = str(image.relative_to(image.parents[3])).replace("\\", "/")
            certificate.pdf_sha256 = digest
            certificate.published_at = timezone.now()
            certificate.save()
        with transaction.atomic():
            current = GenerationTask.objects.select_for_update().get(pk=task.pk)
            if current.lease_token != lease_token or current.status != GenerationTask.Status.RUNNING:
                raise RuntimeError("任务租约已失效，旧 worker 停止写入")
            current.processed = Certificate.objects.filter(
                award__version=current.version, published_at__isnull=False
            ).count()
            current.lease_expires_at = timezone.now() + timedelta(minutes=10)
            current.save(update_fields=["processed", "lease_expires_at", "updated_at"])
    with transaction.atomic():
        current = GenerationTask.objects.select_for_update().get(pk=task.pk)
        if current.lease_token != lease_token:
            raise RuntimeError("任务租约已由其他 worker 接管")
        current.status = GenerationTask.Status.DONE
        current.error = ""
        current.save(update_fields=["status", "error", "updated_at"])
        current.version.batch.status = AwardBatch.Status.ISSUED
        current.version.batch.save(update_fields=["status", "updated_at"])
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
