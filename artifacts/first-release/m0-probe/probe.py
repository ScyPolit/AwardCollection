from __future__ import annotations
import json, hashlib, os, platform, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from fontTools.ttLib import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as RLTTFont
from reportlab.pdfgen import canvas
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec
from pyhanko.sign.signers import PdfSignatureMetadata, PdfSigner
from pyhanko_certvalidator import ValidationContext
from pyhanko.sign.validation import validate_pdf_signature
import fitz

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; EVID=ROOT/'evidence'; KEYS=ROOT/'test-keys'
for p in (OUT,EVID,KEYS): p.mkdir(parents=True,exist_ok=True)
FONT=Path(os.environ.get('M0_FONT',r'C:\Windows\Fonts\Deng.ttf'))
PW=b'm0-test-only'

def sha256(p):
    h=hashlib.sha256();
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def font_coverage(text):
    font=TTFont(str(FONT),fontNumber=0,lazy=True)
    cmap={cp for t in font['cmap'].tables for cp in t.cmap}
    missing=sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cmap})
    return missing

def wrap_chars(text,font,size,max_w):
    lines=[]
    for para in text.splitlines() or ['']:
        line=''
        for ch in para:
            cand=line+ch
            if line and pdfmetrics.stringWidth(cand,font,size)>max_w:
                lines.append(line); line=ch
            else: line=cand
        lines.append(line)
    return lines

def fit_text(text,font,box,max_size,min_size,leading_ratio=1.35):
    x,y,w,h=box
    for half in range(int(max_size*2),int(min_size*2)-1,-1):
        size=half/2; lines=wrap_chars(text,font,size,w); leading=size*leading_ratio
        widths=[pdfmetrics.stringWidth(line,font,size) for line in lines]
        if len(lines)*leading<=h and max(widths,default=0)<=w:
            return {'fits':True,'font_size':size,'lines':lines,'leading':leading,'max_width':max(widths,default=0),'box':[x,y,w,h],'used_height':len(lines)*leading}
    lines=wrap_chars(text,font,min_size,w)
    return {'fits':False,'font_size':min_size,'lines':lines,'leading':min_size*leading_ratio,'max_width':max([pdfmetrics.stringWidth(line,font,min_size) for line in lines],default=0),'box':[x,y,w,h],'used_height':len(lines)*min_size*leading_ratio}

def render():
    font_name='M0Chinese'; pdfmetrics.registerFont(RLTTFont(font_name,str(FONT)))
    page=(842,595)
    members='、'.join(['张晨曦','李若水','王思远','赵清和','陈星野','周明澈','吴知夏','郑云舟','孙景行','何书瑶','林望舒','徐嘉言','高予安','郭青禾','罗嘉树','梁清欢','宋知遥','谢临川'])
    work='面向多部门协同治理场景的校园竞赛电子证书可信签发、长文本自适应排版与可追溯验证关键技术研究及示范应用'
    all_text='校赛电子证书 测试专用 '+members+work+'一等奖 证书编号：2026-M0-000001'
    missing=font_coverage(all_text)
    boxes={'work':(150,315,542,72),'members':(150,220,542,78)}
    results={'font_path':str(FONT),'font_sha256':sha256(FONT),'missing_glyphs':missing,'boxes':{},'page_size_pt':page}
    for key,text,maxs,mins in [('work',work,24,12),('members',members,22,10)]: results['boxes'][key]=fit_text(text,font_name,boxes[key],maxs,mins)
    unsigned=OUT/'unsigned.pdf'; c=canvas.Canvas(str(unsigned),pagesize=page,pageCompression=1)
    c.setStrokeColorRGB(.1,.3,.55); c.setLineWidth(5); c.rect(25,25,page[0]-50,page[1]-50)
    c.setFont(font_name,16); c.drawCentredString(page[0]/2,545,'校赛电子证书 · M0 测试专用')
    c.setFont(font_name,34); c.drawCentredString(page[0]/2,480,'获 奖 证 书')
    c.setFont(font_name,18); c.drawString(85,415,'兹证明测试团队在本次竞赛中荣获一等奖，作品名称：')
    for key in ('work','members'):
        r=results['boxes'][key]; x,y,w,h=r['box']; c.setStrokeColorRGB(.7,.7,.7); c.rect(x,y,w,h)
        c.setFont(font_name,r['font_size']); ty=y+h-r['leading'];
        for line in r['lines']:
            c.drawString(x,ty,line); ty-=r['leading']
    c.setFont(font_name,14); c.drawString(85,275,'团队成员：')
    c.drawString(85,105,'证书编号：2026-M0-000001'); c.drawRightString(755,105,'2026年11月6日')
    c.setFont(font_name,10); c.drawCentredString(page[0]/2,55,'此文件仅用于技术验证，不代表任何学校或部门正式签发。')
    c.save()
    results['checks']={'font_complete':len(missing)==0,'all_boxes_fit':all(r['fits'] for r in results['boxes'].values()),'pdf_pages':len(fitz.open(unsigned))}
    doc=fitz.open(unsigned); pix=doc[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False); pix.save(OUT/'unsigned-preview.png'); doc.close()
    results['artifacts']={'unsigned.pdf':{'sha256':sha256(unsigned),'bytes':unsigned.stat().st_size},'unsigned-preview.png':{'sha256':sha256(OUT/'unsigned-preview.png'),'bytes':(OUT/'unsigned-preview.png').stat().st_size}}
    (EVID/'layout-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results

def make_pfx(label,filename):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME,'CN'),x509.NameAttribute(NameOID.ORGANIZATION_NAME,'AwardCollection M0 Test'),x509.NameAttribute(NameOID.COMMON_NAME,label)])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=365)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).add_extension(x509.KeyUsage(digital_signature=True,content_commitment=True,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=None,decipher_only=None),critical=True).sign(key,hashes.SHA256()))
    data=pkcs12.serialize_key_and_certificates(label.encode(),key,cert,None,serialization.BestAvailableEncryption(PW))
    p=KEYS/filename; p.write_bytes(data)
    return p,cert

def add_sig(src,dst,pfx,field,box):
    signer=signers.SimpleSigner.load_pkcs12(str(pfx),passphrase=PW)
    with open(src,'rb') as inf, open(dst,'wb') as outf:
        w=IncrementalPdfFileWriter(inf)
        spec=SigFieldSpec(sig_field_name=field,on_page=0,box=box)
        meta=PdfSignatureMetadata(field_name=field,md_algorithm='sha256',reason='M0 多部门增量签名技术验证',location='测试环境')
        PdfSigner(meta,signer=signer,new_field_spec=spec).sign_pdf(w,output=outf)

def sign_and_validate():
    p1,c1=make_pfx('测试部门甲', 'dept-a-test.p12'); p2,c2=make_pfx('测试部门乙','dept-b-test.p12')
    add_sig(OUT/'unsigned.pdf',OUT/'signed-dept-a.pdf',p1,'DeptA_Signature',(80,125,260,180))
    add_sig(OUT/'signed-dept-a.pdf',OUT/'signed-final.pdf',p2,'DeptB_Signature',(580,125,760,180))
    roots=[]
    for c in (c1,c2):
        from asn1crypto import x509 as ax509
        roots.append(ax509.Certificate.load(c.public_bytes(serialization.Encoding.DER)))
    vc=ValidationContext(trust_roots=roots,allow_fetching=False)
    with open(OUT/'signed-final.pdf','rb') as f:
        r=PdfFileReader(f); sigs=r.embedded_signatures; rows=[]
        for s in sigs:
            st=validate_pdf_signature(s,signer_validation_context=vc)
            rows.append({'field_name':s.field_name,'intact':bool(st.intact),'valid':bool(st.valid),'trusted':bool(st.trusted),'bottom_line':bool(st.bottom_line),'modification_level':str(st.modification_level),'coverage':str(st.coverage),'summary':st.summary()})
    result={'signature_count':len(rows),'signatures':rows,'checks':{'two_signatures':len(rows)==2,'all_intact':all(x['intact'] for x in rows),'all_valid':all(x['valid'] for x in rows),'all_trusted_in_test_context':all(x['trusted'] for x in rows),'all_bottom_line':all(x['bottom_line'] for x in rows)},'artifacts':{p.name:{'sha256':sha256(p),'bytes':p.stat().st_size} for p in [OUT/'signed-dept-a.pdf',OUT/'signed-final.pdf']},'trust_note':'仅在显式信任本次生成的两张自签测试根证书的 ValidationContext 中 trusted；不代表操作系统或 Adobe 默认信任。'}
    (EVID/'signature-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def main():
    layout=render(); signatures=sign_and_validate()
    overall={'layout_pass':layout['checks']['font_complete'] and layout['checks']['all_boxes_fit'],'multisign_pass':all(signatures['checks'].values())}
    (EVID/'overall.json').write_text(json.dumps(overall,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(overall,ensure_ascii=False))
if __name__=='__main__': main()
