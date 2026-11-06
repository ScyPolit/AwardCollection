"""Final deployment and maintenance audit; run on the target Docker host."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import zlib

project = Path('/opt/awardcollection-v1-test/app')


def run(args, cwd=project):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


release = json.loads((project / 'runtime/release-status.json').read_text())
assert release['stage'] == 'done'
containers = {}
for service in ('api', 'worker', 'web', 'db'):
    item = json.loads(run(['docker', 'inspect', f'awardcollection-v1-test-{service}-1']))[0]
    containers[service] = {
        'created': item['Created'],
        'image': item['Image'],
        'revision': item['Config']['Labels'].get('org.opencontainers.image.revision'),
        'state': item['State']['Status'],
        'health': item['State'].get('Health', {}).get('Status'),
        'volumes': [m['Name'] for m in item['Mounts'] if m['Type'] == 'volume'],
        'logging': item['HostConfig']['LogConfig'],
    }
    assert containers[service]['state'] == 'running'
    if service != 'db':
        assert containers[service]['revision'] == release['revision']
        assert containers[service]['logging']['Config']['max-size'] == '10m'

code = '''import hashlib,json
from django.conf import settings
from awards.models import AwardBatch,Certificate
q=Certificate.objects.filter(award__version__batch_id=2)
data={'debug':settings.DEBUG,'historical':{'status':AwardBatch.objects.get(pk=2).status,'records':q.count(),'pdf':sum(c.pdf.storage.exists(c.pdf.name) for c in q),'png':sum(c.image.storage.exists(c.image.name) for c in q),'published':q.filter(published_at__isnull=False).count()},'samples':[],'new_batches':[]}
for number in ['2026-AC-00000003','2026-AC-00002503','2026-AC-00005002']:
 c=q.get(number=number); digest=hashlib.sha256(c.pdf.read()).hexdigest(); data['samples'].append({'number':number,'sha256':digest,'matches_record':digest==c.pdf_sha256})
for batch_id in [3,4]:
 b=AwardBatch.objects.get(pk=batch_id); records=Certificate.objects.filter(award__version__batch=b)
 data['new_batches'].append({'id':b.id,'status':b.status,'certificates':list(records.values('number','pdf_sha256','published_at'))})
print('AUDIT_DATA='+json.dumps(data,default=str))
'''
output = run(['docker', 'compose', '-p', 'awardcollection-v1-test', 'exec', '-T', 'api', 'python', 'manage.py', 'shell', '-c', code])
data = json.loads(next(line.split('=', 1)[1] for line in output.splitlines() if line.startswith('AUDIT_DATA=')))
assert not data['debug']
assert data['historical'] == {'status': 'issued', 'records': 5000, 'pdf': 5000, 'png': 5000, 'published': 5000}
assert all(item['matches_record'] for item in data['samples'])
assert all(item['status'] == 'issued' and len(item['certificates']) == 2 for item in data['new_batches'])
backup = Path(release['backup'])
assert (backup / 'COMPLETE').is_file()
checksums = run(['sha256sum', '-c', 'SHA256SUMS'], cwd=backup)
assert (project / 'runtime/postgres-regression-final.exit').read_text().strip() == '0'
tests = (project / 'runtime/postgres-regression-final.log').read_text()
assert 'Ran 32 tests' in tests and '\nOK\n' in tests
timer = run(['systemctl', 'is-active', 'awardcollection-maintenance.timer'])
assert timer == 'active'
result = {
    'release': release, 'containers': containers, 'data': data,
    'backup': {'path': str(backup), 'checksums': checksums, 'files': {p.name: p.stat().st_size for p in backup.iterdir()}},
    'timer': timer, 'timer_enabled': run(['systemctl', 'is-enabled', 'awardcollection-maintenance.timer']),
    'postgres_tests': tests,
    'cleanup': run(['sh', str(project / 'deploy/maintenance.sh'), 'cleanup']),
}
(project / 'runtime/final-audit.json').write_text(json.dumps(result, indent=2))
print('RELEASE_AUDIT=' + base64.b64encode(zlib.compress(json.dumps(result).encode())).decode())
