from pathlib import Path
import hashlib,json,zipfile
import fitz
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
root=Path('artifacts/usability-v2-20261106');proof=[]
for number in (5009,5010):
 p=root/f'target-{number}.pdf'
 with p.open('rb') as file:
  reader=PdfFileReader(file);signatures=[]
  for signature in reader.embedded_signatures:
   status=validate_pdf_signature(signature);signatures.append({'intact':status.intact,'valid':status.valid,'trusted':status.trusted})
 assert len(signatures)==2 and all(s['intact'] and s['valid'] for s in signatures)
 doc=fitz.open(p);page=doc[0];text=page.get_text();drawings=page.get_drawings()
 assert len(drawings)>=5 and any(span['type']==1 for span in page.get_texttrace())
 assert f'2026-AC-{number:08}' in text and '获奖证书' in text and '�' not in text
 fonts=sorted({font[3] for font in page.get_fonts()})
 assert all(any(name in font for font in fonts) for name in ['Zhuque','UMing','UKai','LiberationSerif','LiberationSans','LiberationMono'])
 proof.append({'file':p.name,'signatures':signatures,'fonts':fonts,'vector_paths':len(drawings),'bold_stroke_present':True,'text':text,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
with zipfile.ZipFile(root/'target-batch-6.zip') as archive:
 assert len(archive.namelist())==4
 for name in archive.namelist():
  number=int(Path(name).stem.split('-')[-1]);assert archive.read(name)==(root/f'target-{number}{Path(name).suffix}').read_bytes()
(root/'target-styles-signatures-fonts-zip.json').write_text(json.dumps({'certificates':proof,'zip_identical':True},ensure_ascii=False,indent=2),encoding='utf8')
print('Styled output: four valid intact signatures, 5+ vector paths, bold strokes, extractable Chinese, embedded fonts and identical ZIP')
