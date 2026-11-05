import time
from django.core.management.base import BaseCommand
from awards.services import claim_task


class Command(BaseCommand):
    help = "Run the persistent certificate generation worker"

    def handle(self, *args, **options):
        self.stdout.write("worker started")
        while True:
            task = claim_task()
            if task is None:
                time.sleep(2)
                continue
            task.status = task.Status.FAILED
            task.error = "Renderer is not configured for this task version"
            task.save(update_fields=["status", "error", "updated_at"])
