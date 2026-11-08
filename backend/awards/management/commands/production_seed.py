import json
from django.core.management.base import BaseCommand, CommandError
from awards.production_seed import export_seed, import_seed, read_seed, reset_business


class Command(BaseCommand):
    help = "显式导出私有生产初始化包、初始化全新数据库，或在完整备份后清理测试业务；不会自动执行"

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=["export", "inspect", "import", "reset"])
        parser.add_argument("--output")
        parser.add_argument("--superuser-id", type=int)
        parser.add_argument("--bundle")
        parser.add_argument("--sha256")
        parser.add_argument("--verified-backup")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        operation = options["operation"]
        if operation == "export":
            if not options["output"] or not options["superuser_id"]:
                raise CommandError("导出必须指定 --output 与 --superuser-id")
            report = export_seed(options["output"], options["superuser_id"])
        else:
            if not options["bundle"] or not options["sha256"]:
                raise CommandError("必须指定 --bundle 与来自可信渠道的 --sha256")
            if operation == "inspect":
                manifest, _ = read_seed(options["bundle"], options["sha256"])
                report = {"valid": True, "private": True, "media_files": len(manifest["files"])}
            elif operation == "reset":
                report = reset_business(options["bundle"], options["sha256"], backup=options["verified_backup"], apply=options["apply"])
            else:
                if not options["apply"]:
                    raise CommandError("导入全新数据库必须显式指定 --apply")
                report = import_seed(options["bundle"], options["sha256"])
        self.stdout.write(json.dumps(report, ensure_ascii=False))
