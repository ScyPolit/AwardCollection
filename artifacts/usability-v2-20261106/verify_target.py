"""Verify the deployed UI/role/font release without changing historical batches."""
import base64, hashlib, json, re, subprocess, urllib.request, zlib
from pathlib import Path
project=Path('/opt/awardcollection-v1-test/app')
revision='246348db2092261433cfe2f8bafc338f62f03a64'
def run(args,cwd=project):
 return subprocess.run(args,cwd=cwd,text=True,capture_output=True,check=True,timeout=300).stdout.strip()
release=json.loads((project/'runtime/release-status.json').read_text())
assert release['stage']=='done' and release['revision']==revision
containers={}
for service in ('api','worker','web','db'):
 item=json.loads(run(['docker','inspect','awardcollection-v1-test-'+service+'-1']))[0]
 containers[service]={'created':item['Created'],'image':item['Image'],'revision':item['Config']['Labels'].get('org.opencontainers.image.revision'),'state':item['State']['Status'],'health':item['State'].get('Health',{}).get('Status'),'volumes':[m['Name'] for m in item['Mounts'] if m['Type']=='volume'],'logging':item['HostConfig']['LogConfig']}
 assert containers[service]['state']=='running'
 if service!='db':
  assert containers[service]['revision']==revision
  assert containers[service]['logging']['Config']=={'max-file':'5','max-size':'10m'}
assert containers['db']['created']=='2026-11-05T19:20:01.632110387Z'
assert set(containers['api']['volumes'])=={'awardcollection-v1-test_media_data','awardcollection-v1-test_backup_data'}
assert containers['db']['volumes']==['awardcollection-v1-test_db_data']
code='''import hashlib,json
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from awards.models import AwardBatch,Certificate,CertificateFont,GenerationTask,DepartmentMembership
from awards.fonts import ASSETS,font_file
from awards.permissions import user_roles
q=Certificate.objects.filter(award__version__batch_id=2)
data={'debug':settings.DEBUG,'historical':{'status':AwardBatch.objects.get(pk=2).status,'records':q.count(),'pdf':sum(c.pdf.storage.exists(c.pdf.name) for c in q),'png':sum(c.image.storage.exists(c.image.name) for c in q),'published':q.filter(published_at__isnull=False).count()},'samples':[],'new_batch':{},'fonts':[]}
for number in ['2026-AC-00000003','2026-AC-00002503','2026-AC-00005002']:
 c=q.get(number=number); digest=hashlib.sha256(c.pdf.read()).hexdigest(); data['samples'].append({'number':number,'sha256':digest,'matches_record':digest==c.pdf_sha256})
b=AwardBatch.objects.get(pk=5); task=GenerationTask.objects.get(version__batch=b)
records=[]
for c in Certificate.objects.filter(award__version__batch=b).order_by('number'):
 digest=hashlib.sha256(c.pdf.read()).hexdigest(); records.append({'number':c.number,'pdf_sha256':digest,'matches_record':digest==c.pdf_sha256,'png_exists':c.image.storage.exists(c.image.name),'published_at':str(c.published_at)})
data['new_batch']={'id':b.pk,'status':b.status,'task':{'status':task.status,'processed':task.processed,'total':task.total,'attempts':task.attempts,'error':task.error},'certificates':records}
for f in json.loads((ASSETS/'manifest.json').read_text()):
 p=font_file(f['id']); persisted=Path(settings.MEDIA_ROOT)/'protected/font-library/builtin'/(f['sha256']+'.ttf'); data['fonts'].append({'id':f['id'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'expected':f['sha256'],'persisted':persisted.is_file()})
f=CertificateFont.objects.get(pk='29d12439831b7f59194efec85872f24f54eff05738933f9a860220d2abff88ba')
data['imported_font']={'name':f.name,'active':f.active,'sha256':hashlib.sha256(f.file.read()).hexdigest(),'expected':f.pk}
u=get_user_model().objects.get(username='test_v2_owner_20261106')
data['independent_owner']={'roles':user_roles(u),'memberships':DepartmentMembership.objects.filter(user=u).count()}
b=AwardBatch.objects.get(pk=6);task=GenerationTask.objects.get(version__batch=b)
styled=[]
import fitz
for c in Certificate.objects.filter(award__version__batch=b).order_by('number'):
 digest=hashlib.sha256(c.pdf.read()).hexdigest()
 with fitz.open(c.pdf.path) as document:
  paths=len(document[0].get_drawings());bold=any(span['type']==1 for span in document[0].get_texttrace())
 styled.append({'number':c.number,'pdf_sha256':digest,'matches_record':digest==c.pdf_sha256,'png_exists':c.image.storage.exists(c.image.name),'published_at':str(c.published_at),'vector_paths':paths,'bold_strokes':bold})
canvas=task.version.snapshot.get('template') or task.version.template_version.canvas
font=CertificateFont.objects.get(pk='6b3809450cf6253b36d157198dc15004a5fbade9abad5543c377feb7bb29139c')
data['styled_batch']={'id':b.pk,'status':b.status,'task':{'status':task.status,'processed':task.processed,'total':task.total,'attempts':task.attempts,'error':task.error},'certificates':styled,'template_version':task.version.template_version_id,'styles':{key:canvas['layers'][0].get(key) for key in ('bold','italic','underline')},'shapes':sorted(layer['kind'] for layer in canvas['layers'] if layer['type']=='shape')}
data['owner_import']={'creator':font.created_by.username,'sha256':hashlib.sha256(font.file.read()).hexdigest(),'expected':font.pk,'active':font.active}
print('DATA='+json.dumps(data,default=str))
'''
output=run(['docker','compose','-p','awardcollection-v1-test','exec','-T','api','python','manage.py','shell','-c',code])
data=json.loads(next(line.split('=',1)[1] for line in output.splitlines() if line.startswith('DATA=')))
assert not data['debug']
assert data['historical']=={'status':'issued','records':5000,'pdf':5000,'png':5000,'published':5000}
assert all(s['matches_record'] for s in data['samples'])
assert data['new_batch']['status']=='issued' and data['new_batch']['task']=={'status':'done','processed':2,'total':2,'attempts':1,'error':''}
assert len(data['new_batch']['certificates'])==2 and all(c['matches_record'] and c['png_exists'] for c in data['new_batch']['certificates'])
assert len({c['published_at'] for c in data['new_batch']['certificates']})==1
assert len(data['fonts'])==7 and all(f['sha256']==f['expected'] and f['persisted'] for f in data['fonts'])
assert data['imported_font']['sha256']==data['imported_font']['expected']
assert data['independent_owner']=={'roles':['owner'],'memberships':0}
assert data['styled_batch']['status']=='issued'
assert data['styled_batch']['styles']=={'bold':True,'italic':True,'underline':True}
assert data['styled_batch']['shapes']==['ellipse','freehand','line','rect']
assert data['styled_batch']['task']=={'status':'done','processed':2,'total':2,'attempts':1,'error':''}
assert len(data['styled_batch']['certificates'])==2 and all(c['matches_record'] and c['png_exists'] and c['bold_strokes'] and c['vector_paths']>=5 for c in data['styled_batch']['certificates'])
assert data['owner_import']['creator']=='test_v2_owner_20261106' and data['owner_import']['sha256']==data['owner_import']['expected']
tests=(project/'runtime/usability-v3-tests.log').read_text()
assert (project/'runtime/usability-v3-tests.exit').read_text().strip()=='0'
assert 'Ran 50 tests' in tests and '\nOK\n' in tests
focused=(project/'runtime/usability-v3-final-tests.log').read_text()
assert (project/'runtime/usability-v3-final-tests.exit').read_text().strip()=='0' and 'Ran 3 tests' in focused and '\nOK\n' in focused
backup=Path(release['backup'])
assert (backup/'COMPLETE').is_file()
checksums=run(['sha256sum','-c','SHA256SUMS'],cwd=backup)
health=json.loads(urllib.request.urlopen('http://127.0.0.1:18080/api/v1/health/').read())
assert health['version']==revision and health['status']=='ok'
assert run(['systemctl','is-active','awardcollection-maintenance.timer'])=='active'
assert run(['systemctl','is-enabled','awardcollection-maintenance.timer'])=='enabled'
result={'focused_tests':focused,'final_backend_tree':'de1004a8f03600792f7d8ae4130bcd1ebd16162b','release':release,'health':health,'containers':containers,'data':data,'backup':{'path':str(backup),'checksums':checksums,'files':{p.name:p.stat().st_size for p in backup.iterdir()}},'postgres_tests':tests,'backend_test_revision':'623c35f3a8eb5ee4a2f5f7b0fb6f0d98e1261717','backend_git_tree':'c47ba83ac4cee2af0787ac2e4993e30275607c75','timer':'active/enabled'}
(project/'runtime/usability-v3-final-audit.json').write_text(json.dumps(result,indent=2))
print('V3_FINAL_AUDIT='+base64.b64encode(zlib.compress(json.dumps(result).encode())).decode())
