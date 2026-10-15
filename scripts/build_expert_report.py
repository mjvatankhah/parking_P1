import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
import arabic_reshaper
from bidi.algorithm import get_display
import pymupdf as fitz
root=Path(__file__).resolve().parents[1]
pages=json.loads((root/'reports/alpr_expert_review_content_20261015.json').read_text())
status=root/'reports/alpr_expert_review_status_20261015.txt'
status=status.read_text() if status.exists() else 'Implementation pending; baseline diagnosis is complete.'
out=root/'output/pdf';out.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('Fa','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('FaBold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
def visual(s):return get_display(arabic_reshaper.reshape(s))
def wrap(s,width,size):
 lines=[];line=''
 for word in s.split():
  trial=(line+' '+word).strip()
  if pdfmetrics.stringWidth(visual(trial),'Fa',size)>width and line:lines.append(line);line=word
  else:line=trial
 if line:lines.append(line)
 return lines
path=out/'alpr_architecture_expert_review_20261015.pdf'
c=canvas.Canvas(str(path),pagesize=A4);c.setTitle('ALPR architecture and evaluation for expert review')
w,h=A4
for n,page in enumerate(pages,1):
 y=h-44;c.setFillColorRGB(0,0,0);c.setFont('FaBold',15);c.drawRightString(w-42,y,visual(page['title']));y-=25
 c.setFont('Fa',9);c.drawRightString(w-42,y,visual(page['subtitle']));y-=26
 for heading,body in page['sections']:
  body=body.replace('STATUS_PLACEHOLDER',status)
  c.setFont('FaBold',10.8);c.drawRightString(w-42,y,visual(heading));y-=18
  c.setFont('Fa',10.2)
  for line in wrap(body,w-84,10.2):
   c.drawRightString(w-42,y,visual(line));y-=16
  y-=11
 assert y>40,(n,y)
 c.setFont('Fa',8);c.drawCentredString(w/2,24,visual(str(n)+' / 3'));c.showPage()
c.save()
doc=fitz.open(path);assert len(doc)==3
for i,p in enumerate(doc):p.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(root/f'tmp/pdfs/report-page-{i+1}.png')
print(path)
