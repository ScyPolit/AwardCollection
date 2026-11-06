from pathlib import Path
import hashlib,json,zipfile
import fitz
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
root=Path('artifacts/usability-v2-20261106')
proof=[]
for number in (5007,5008):
 p=root/f'target-{number}.pdf'
 with p.open('rb') as f:
  reader=PdfFileReader(f)
  signatures=[]
  for signature in reader.embedded_signatures:
   status=validate_pdf_signature(signature)
   signatures.append({'intact':status.intact,'valid':status.valid,'trusted':status.trusted})
  assert len(signatures)==2 and all(s['intact'] and s['valid'] for s in signatures)
 doc=fitz.open(p)
 text=''.join(page.get_text() for page in doc)
 fonts=sorted({font[3] for page in doc for font in page.get_fonts()})
 assert f'2026-AC-{number:08}' in text
 assert 'Innovation Award / TEST ONLY' in text
 assert '�' not in text
 assert all(any(name in f for f in fonts) for name in ['Zhuque','UMing','UKai','LiberationSerif','LiberationSans','LiberationMono'])
 proof.append({'file':p.name,'signatures':signatures,'fonts':fonts,'text':text,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
with zipfile.ZipFile(root/'target-batch-5.zip') as archive:
 assert len(archive.namelist())==4
 for name in archive.namelist():
  number=int(Path(name).stem.split('-')[-1])
  actual=(root/f'target-{number}{Path(name).suffix}').read_bytes()
  assert archive.read(name)==actual
(root/'target-signatures-fonts-zip.json').write_text(json.dumps({'certificates':proof,'zip_identical':True},ensure_ascii=False,indent=2),encoding='utf8')
print('Two PDFs: all four signatures intact/valid, all configured font families embedded, ZIP identical')
