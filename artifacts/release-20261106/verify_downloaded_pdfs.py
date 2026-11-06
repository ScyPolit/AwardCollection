import hashlib,json,logging
from pathlib import Path
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
import fitz
logging.getLogger('pyhanko.sign.validation.generic_cms').setLevel(logging.CRITICAL)
logging.getLogger('pyhanko_certvalidator').setLevel(logging.CRITICAL)
root=Path(__file__).resolve().parent
records=[]
for p in sorted(root.glob('issued-*.pdf')):
 with p.open('rb') as f:
  sigs=PdfFileReader(f).embedded_signatures
  checks=[]
  for sig in sigs:
   assert list(sig.sig_field["/Rect"])==[0,0,0,0]
   s=validate_pdf_signature(sig)
   assert s.intact and s.valid,(p.name,s)
   checks.append({'field':sig.field_name,'intact':s.intact,'valid':s.valid,'trusted':s.trusted})
 assert len(checks)==2
 with fitz.open(p) as doc:
  text=''.join(pg.get_text() for pg in doc)
  assert 'TEST ONLY' in text and '首版验收' in text,(p.name,text)
  assert 'Timestamp:' not in text
  if p.stem.endswith('5006'):
   assert '这是用于验证较长作品名称能够自动排版且保留全部内容的测试作品名称' in text.replace('\n','')
  images=len(doc[0].get_images())
  assert images>=3,images
 records.append({'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'signatures':checks,'embedded_images':images,'text':text})
assert len(records)==2,records
(root/'signature-verification.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'files':len(records),'signatures':4,'intact':True,'valid':True},ensure_ascii=False))
