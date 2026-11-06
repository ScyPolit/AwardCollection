import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Remove expired files from MEDIA_ROOT/temporary without touching formal records"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1")
        root = (Path(settings.MEDIA_ROOT) / "temporary").resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        if root.parent != media_root:
            raise CommandError("temporary directory escaped MEDIA_ROOT")
        if not root.exists():
            self.stdout.write("temporary directory does not exist")
            return
        cutoff = time.time() - days * 86400
        files = [path for path in root.rglob("*") if path.is_file() and path.stat().st_mtime < cutoff]
        for path in files:
            if not options["dry_run"]:
                path.unlink()
        if not options["dry_run"]:
            for directory in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        action = "would remove" if options["dry_run"] else "removed"
        self.stdout.write(self.style.SUCCESS(f"{action} {len(files)} expired temporary files"))
