import html,json
from pathlib import Path
p=Path(__file__).resolve().parent
rows=json.loads((p/'all_readings.json').read_text())
body=['<!doctype html><meta charset="utf-8"><title>بررسی دو خودرو</title><style>body{font:18px sans-serif;background:#eee;margin:30px}section{background:white;padding:20px;margin:20px 0}img{width:400px;image-rendering:auto}code{direction:ltr;display:inline-block}</style><h1 dir="rtl">تصاویر و خوانش‌های دو خودروی اول</h1>']
for r in rows:
    n,f=r['car'],r['frame']; text=html.escape(json.dumps(r['readings'],ensure_ascii=False))
    body.append(f'<section><h2>Car {n} / frame {f}</h2><p>{text}</p><p>Raw</p><img src="event_{n}_frame_{f}_raw.jpg">')
    if (p/f'event_{n}_frame_{f}_prepared.jpg').exists(): body.append(f'<p>OCR input</p><img src="event_{n}_frame_{f}_prepared.jpg">')
    body.append('</section>')
(p/'gallery.html').write_text('\n'.join(body))
