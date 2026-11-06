import hashlib
import json
import os
import shutil
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from awards.fonts import ASSETS


class Command(BaseCommand):
    help = 'Keep exact built-in fonts in the media volume for offline rendering and backup'

    def handle(self, *args, **options):
        root = Path(settings.MEDIA_ROOT) / 'protected/font-library/builtin'
        root.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((ASSETS / 'manifest.json').read_text(encoding='utf8'))
        for item in manifest:
            source = ASSETS / item['file']
            target = root / (item['sha256'] + '.ttf')
            if hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError('Built-in font checksum mismatch: ' + item['id'])
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256']:
                continue
            temporary = target.with_suffix(f'.{os.getpid()}.tmp')
            shutil.copyfile(source, temporary)
            temporary.replace(target)
        self.stdout.write(f'{len(manifest)} verified fonts available in the media volume')
