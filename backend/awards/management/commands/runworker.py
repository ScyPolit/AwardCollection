import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from awards.models import AwardBatch, Certificate, GenerationTask
from awards.renderer import render_certificate
from awards.services import allocate_number, claim_task


class Command(BaseCommand):
    help = "Run the persistent certificate generation worker"

    def handle(self, *args, **options):
        self.stdout.write("worker started")
        while True:
            task = claim_task()
            if task is None:
                time.sleep(2)
                continue
            try:
                for award in task.version.awards.order_by("source_row"):
                    with transaction.atomic():
                        certificate = Certificate.objects.select_for_update().filter(award=award).first()
                        if certificate is None:
                            certificate = Certificate.objects.create(award=award, number=allocate_number())
                    if not certificate.pdf:
                        pdf, image, digest = render_certificate(award, certificate.number)
                        certificate.pdf.name = str(pdf.relative_to(pdf.parents[3]))
                        certificate.image.name = str(image.relative_to(image.parents[3]))
                        certificate.pdf_sha256 = digest
                        certificate.published_at = timezone.now()
                        certificate.save()
                    task.processed += 1
                    task.lease_expires_at = timezone.now() + timedelta(minutes=10)
                    task.save(update_fields=["processed", "lease_expires_at", "updated_at"])
                task.status = GenerationTask.Status.DONE
                task.version.batch.status = AwardBatch.Status.ISSUED
                task.version.batch.save(update_fields=["status", "updated_at"])
                task.save(update_fields=["status", "updated_at"])
            except Exception as exc:
                task.status = GenerationTask.Status.FAILED
                task.error = str(exc)
                task.save(update_fields=["status", "error", "updated_at"])
