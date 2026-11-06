"""Run the final source against an isolated PostgreSQL test DB while images build.

The disposable container installs the exact production constraints into /tmp.
No production media is mounted and the image entrypoint is bypassed.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile

BASE = Path('/opt/awardcollection-v1-test')
PROJECT = BASE / 'app'
REVISION = 'dd9cb841e43bbc0d783471f5e4caa617cff0e35c'
ARCHIVE_SHA = '1aac1454badea23c1058a5cc11224563fb71a02f11ebf7e61a8d9c575b60465a'
archive = BASE / 'incoming' / (REVISION + '.tar.gz')
assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA
directory = BASE / 'qa' / ('v4-regression-' + secrets.token_hex(4))
directory.mkdir(parents=True, mode=0o700)
with tarfile.open(archive) as bundle:
    bundle.extractall(directory, filter='data')
source = directory / ('AwardCollection-' + REVISION) / 'backend'
manifest = json.loads((source / 'font-assets/manifest.json').read_text())
for font in manifest:
    cached = BASE / 'font-cache' / font['file']
    if not cached.is_file():
        subprocess.run(['docker','cp',f"awardcollection-v1-test-api-1:/srv/media/protected/font-library/builtin/{font['sha256']}.ttf",str(cached)],check=True,stdout=subprocess.DEVNULL)
    assert hashlib.sha256(cached.read_bytes()).hexdigest() == font['sha256']
    shutil.copyfile(cached, source / 'font-assets' / font['file'])
config = {}
for line in (PROJECT / '.env').read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        config[key] = value.strip().strip('"').strip("'")
image = subprocess.check_output(['docker', 'inspect', '--format', '{{.Image}}', 'awardcollection-v1-test-api-1'], text=True).strip()
env = os.environ.copy()
env.update({
    'DATABASE_URL': f"postgresql://{config.get('POSTGRES_USER','awardcollection')}:{config['POSTGRES_PASSWORD']}@db:5432/{config.get('POSTGRES_DB','awardcollection')}",
    'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
    'DJANGO_DEBUG': 'false',
    'DJANGO_ALLOWED_HOSTS': 'testserver,localhost,127.0.0.1',
    'SIGNING_KEY_PASSWORD': secrets.token_urlsafe(24),
    'MEDIA_ROOT': '/tmp/qa-media', 'BACKUP_ROOT': '/tmp/qa-backups',
    'AWARD_TEST_DB': 'test_awardcollection_v4_' + secrets.token_hex(4),
})
test_code = "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from django.db import connections;connections['default'].settings_dict['TEST']['NAME']=os.environ['AWARD_TEST_DB'];from django.core.management import execute_from_command_line;execute_from_command_line(['manage.py','test','awards','--noinput'])"
command = 'python -m venv --system-site-packages /tmp/qa-venv && /tmp/qa-venv/bin/python -m pip install --quiet --no-index --force-reinstall --find-links=/wheels -r /wheels/constraints.txt && cd /testsource && /tmp/qa-venv/bin/python -c ' + "'" + test_code.replace("'", "'\\''") + "'"
args = ['docker','run','--rm','--name','awardcollection-v4-regression','--network','awardcollection-v1-test_internal','--entrypoint','sh','--mount',f'type=bind,source={source},target=/testsource,readonly','--mount',f'type=bind,source={BASE}/wheel-cache/linux-cp312-amd64,target=/wheels,readonly','--memory','2g','--pids-limit','256']
for key in ['DATABASE_URL','DJANGO_SECRET_KEY','DJANGO_DEBUG','DJANGO_ALLOWED_HOSTS','SIGNING_KEY_PASSWORD','MEDIA_ROOT','BACKUP_ROOT','AWARD_TEST_DB']:
    args += ['-e',key]
args += [image,'-c',command]
with (PROJECT / 'runtime/v4-postgres-tests.log').open('w') as output:
    result = subprocess.run(args, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=1800)
(PROJECT / 'runtime/v4-postgres-tests.exit').write_text(str(result.returncode))
print(json.dumps({'exit':result.returncode,'source':REVISION,'test_database':env['AWARD_TEST_DB'],'source_directory':str(directory)}))
