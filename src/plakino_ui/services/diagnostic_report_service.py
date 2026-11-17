"""Owner-only, self-contained diagnostic documents for a committed passage.

The archive is evidence, not a diagnosis of image quality. Decision explanations
come from recorded readings; missing images and historical settings stay unknown.
"""
import base64
from collections import Counter
from datetime import datetime
import html
import io
import json
import math
import os
from pathlib import Path
import tempfile

from PIL import Image

from computer_vision_v2.site_time import TEHRAN
from computer_vision_v2.storage.diagnostic_paths import ARCHIVE_ROOT, DOCUMENT_ROOT
from plakino_ui.services.auth_service import auth_service

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATUS = {'read': 'خوانده شد', 'uncertain': 'نامطمئن', 'unread': 'خوانده نشد'}
VARIANTS = {'raw': 'خام', 'geometry': 'اصلاح هندسی', 'padded': 'حاشیه‌دار'}
REASONS = {
    'no_accepted_plate_detection': 'مدل پلاک، کادر قابل‌قبولی پیدا نکرد',
    'below_minimum_size': 'پلاک از حداقل اندازه کوچک‌تر بود',
    'detection_exception': 'خطا در اجرای تشخیص پلاک',
    'geometry_unavailable': 'نسخهٔ هندسی آماده نشد؛ خام همچنان قابل بررسی است',
    'candidate': 'کاندید پلاک آماده شد',
    'no_detection': 'تشخیصی بالاتر از آستانه وجود نداشت',
    'empty_or_touches_vehicle_boundary': 'کادر خالی بود یا به لبهٔ کراپ خودرو رسید',
    'accepted': 'کادر پلاک پذیرفته شد',
}


def eligible(record):
    return record.class_id == 2 and record.recognition_status in ('unread', 'uncertain')


def _e(value):
    return html.escape(str(value if value is not None else 'ثبت نشده'))


def _stamp(value):
    if not value:
        return 'ثبت نشده'
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            return 'منطقهٔ زمانی ثبت نشده'
        return stamp.astimezone(TEHRAN).strftime('%Y-%m-%d · %H:%M:%S')
    except (TypeError, ValueError):
        return 'زمان معتبر ثبت نشده'


def _score(value):
    try:
        return f'{float(value):.3f}' if math.isfinite(float(value)) else 'ثبت نشده'
    except (TypeError, ValueError):
        return 'ثبت نشده'


def decision(readings):
    votes = Counter(r.get('text', '') for r in readings
                    if r.get('valid') and float(r.get('confidence', 0)) >= .8)
    ranked = votes.most_common()
    if not readings:
        reason = 'هیچ خوانش OCR ثبت نشده است؛ تشخیص پلاک و تصاویر خودرو را بررسی کنید.'
    elif not ranked:
        reason = 'هیچ خوانشی هم‌زمان قالب معتبر و اطمینان حداقل ۰٫۸ ندارد.'
    elif ranked[0][1] < 2:
        reason = 'هیچ شماره‌ای حداقل دو رأی معتبر یکسان دریافت نکرده است.'
    elif len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        reason = 'رأی دو یا چند شماره برابر است؛ برندهٔ یکتا وجود ندارد.'
    else:
        reason = 'خوانش‌ها برنده دارند؛ وضعیت نهایی ثبت‌شده نیز جداگانه نمایش داده شده است.'
    return reason, ranked


class ArchiveImages:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.cache = {}

    def read(self, name):
        if not isinstance(name, str) or not name or Path(name).name != name:
            return None
        if name in self.cache:
            return self.cache[name]
        path = (self.directory / name).resolve()
        if path.parent != self.directory or path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            return None
        try:
            if path.stat().st_size > 16_000_000:
                return None
            data = path.read_bytes()
            with Image.open(io.BytesIO(data)) as img:
                width, height = img.size
                if img.format not in ('PNG', 'JPEG'):
                    return None
                mime = 'image/png' if img.format == 'PNG' else 'image/jpeg'
            value = (f'data:{mime};base64,' + base64.b64encode(data).decode('ascii'), width, height)
            self.cache[name] = value
            return value
        except (OSError, ValueError):
            return None

    def figure(self, name, title, boxes=()):
        value = self.read(name)
        if value is None:
            return f'<figure><figcaption>{_e(title)}</figcaption><p class="missing">تصویر ثبت نشده یا در دسترس نیست</p></figure>'
        uri, width, height = value
        visual = f'<img loading="lazy" src="{uri}" alt="{_e(title)}">'
        if boxes:
            overlays = []
            for box, color in boxes:
                try:
                    x1, y1, x2, y2 = map(float, box)
                    if not all(math.isfinite(x) for x in (x1, y1, x2, y2)):
                        continue
                    overlays.append(f'<rect x="{x1}" y="{y1}" width="{max(0,x2-x1)}" height="{max(0,y2-y1)}" '
                                    f'fill="none" stroke="{color}" stroke-width="3" vector-effect="non-scaling-stroke"/>')
                except (TypeError, ValueError):
                    continue
            visual = (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{_e(title)}">'
                      f'<image href="{uri}" width="{width}" height="{height}"/>' + ''.join(overlays) + '</svg>')
        return (f'<figure><figcaption>{_e(title)} <small dir="ltr">{width} × {height} px</small></figcaption>'
                + visual + '</figure>')


def render_report(record, manifest, directory):
    pictures = ArchiveImages(directory)
    samples = sorted(manifest.get('samples', []), key=lambda s: (s.get('ts', 0), s.get('frame_idx', 0)))
    inputs = manifest.get('ocr_inputs', [])
    readings = inputs or manifest.get('result', {}).get('readings', [])
    reason, votes = decision(readings)
    recognition_error = manifest.get('result', {}).get('recognition_error')
    if recognition_error:
        reason = f'اجرای OCR با خطا متوقف شد: {recognition_error}. خوانش‌های ثبت‌شده پیش از خطا در ادامه آمده‌اند.'
    scene = manifest.get('crossing') or {}
    event = manifest.get('event') or {}
    crossing_ts = event.get('ts')
    parts = [f'''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>گزارش تشخیص تردد {_e(record.event_id)}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f2f5f9;color:#19293c;font:16px Tahoma,Arial,sans-serif;line-height:1.9}}
main{{max-width:1280px;margin:auto;padding:28px}}h1{{margin:0;font-size:28px}}h2{{font-size:22px;margin:0 0 15px}}
h3{{font-size:17px}}section,.sample{{background:white;border:1px solid #dbe3ed;border-radius:12px;padding:22px;margin:18px 0}}
.meta,.images,.metrics{{display:flex;gap:18px;flex-wrap:wrap}}.meta>div,.metric{{background:#eef3f9;padding:12px 18px;border-radius:8px}}
.images>figure{{flex:1 1 240px;min-width:0}}figure{{margin:0;padding:10px;background:#f7f9fc;border-radius:8px}}
figcaption{{margin-bottom:10px}}img,svg{{max-width:100%;height:auto;max-height:480px;object-fit:contain;display:block;margin:auto}}
small,.muted{{color:#53667c}}.missing,.warning{{color:#845000;background:#fff6df;padding:10px;border-radius:6px}}
.decision{{border-right:5px solid #e9a824}}nav{{display:flex;gap:18px;flex-wrap:wrap;margin:20px 0}}a{{color:#145eaa}}
table{{border-collapse:collapse;width:100%}}td,th{{text-align:right;padding:10px;border-bottom:1px solid #e4eaf1}}
.table{{overflow:auto}}bdi{{font-family:Tahoma,Arial,sans-serif}}details{{margin:12px 0}}summary{{cursor:pointer;color:#145eaa}}
pre{{direction:ltr;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f8;padding:14px;font-size:12px}}
.tag{{display:inline-block;padding:2px 9px;background:#e3edf9;border-radius:6px}}.yes{{color:#176843}}.no{{color:#9a3b31}}
@media print{{body{{background:white}}main{{padding:0}}nav{{display:none}}section,.sample{{break-inside:avoid}}}}
</style></head><body><main>
<h1>گزارش تشخیص تردد {_e(record.event_id)}</h1>
<p class="muted">از تصویر خودرو تا رأی نهایی OCR · سند مستقل همراه تصاویر</p>
<nav><a href="#summary">نتیجه و علت تصمیم</a><a href="#scene">صحنهٔ عبور</a><a href="#samples">مسیر تصاویر</a><a href="#ocr">خوانش‌های OCR</a><a href="#settings">اطلاعات اجرا</a></nav>
<section id="summary"><div class="meta">
<div>وضعیت: <strong>{_e(STATUS.get(record.recognition_status, record.recognition_status))}</strong></div>
<div>دوربین: <bdi>{_e(record.camera)}</bdi> · {_e(record.direction_label())}</div>
<div>زمان ثبت در سامانه — تهران<br><bdi dir="ltr">{_e(record.date)} · {_e(record.time)}</bdi></div>
</div><p class="decision">{_e(reason)}</p>
<p class="muted">قاعدهٔ تأیید: قالب معتبر، اطمینان حداقل ۰٫۸ و حداقل دو رأی همسان با برتری بر شمارهٔ بعدی. نسخهٔ خام و هندسی یک فریم می‌توانند رأی جدا بدهند. این توضیح علت تصمیم نرم‌افزار است؛ علت تصویری باید از شواهد بررسی شود.</p>
<div class="metrics"><div class="metric">نمونهٔ خودرو: {len(samples)}</div>
<div class="metric">کراپ پلاک موجود: {sum(bool(s.get('raw')) for s in samples)}</div>
<div class="metric">ورودی OCR ثبت‌شده: {len(inputs)}</div></div>''']
    if votes:
        parts.append('<h3>رأی‌های واجد شرایط</h3><div class="table"><table><tr><th>شماره</th><th>تعداد رأی</th></tr>')
        parts.extend(f'<tr><td><bdi>{_e(text)}</bdi></td><td>{count}</td></tr>' for text, count in votes)
        parts.append('</table></div>')
    lost = [(label, manifest.get(key, 0)) for key, label in (
        ('dropped_pending', 'نمونهٔ حذف‌شده از صف'), ('omitted_samples', 'نمونهٔ خارج از سقف آرشیو'),
        ('omitted_images', 'تصویر ذخیره‌نشده به دلیل سقف حافظه'))]
    parts.append('<p class="warning">' + ' · '.join(f'{label}: {_e(count)}' for label, count in lost)
                 + '<br>این شمارنده‌ها همهٔ افت فریم‌های دریافت/ردیابی را پوشش نمی‌دهند. تصویرِ ذخیره‌نشده به معنی نبودن پلاک نیست.</p></section>')
    parts.append('<section id="scene"><h2>۱. صحنهٔ عبور</h2>' + pictures.figure(
        scene.get('image'), 'فریم عبور؛ کادر آبی مربوط به خودروی این تردد است',
        [(scene.get('bbox'), '#26a7ff')] if scene.get('bbox') else []) + '</section>')
    parts.append('<section id="samples"><h2>۲. مسیر تصاویر به ترتیب زمان</h2>'
                 '<p class="muted">زمان نسبی بر اساس زمان منبع و نسبت به عبور از خط است. ابعاد تصاویر عرض × ارتفاع هستند؛ نمایش اندازهٔ واقعی فایل را تغییر نمی‌دهد.</p>')
    if not samples:
        parts.append('<p class="missing">تصاویر نمونهٔ خودرو برای این رویداد آرشیو نشده‌اند.</p>')
    decisions = manifest.get('selection_decisions', [])
    for sample in samples:
        frame = sample.get('frame_idx')
        sources = sample.get('ocr_sources', [])
        relative = ''
        if isinstance(crossing_ts, (int, float)) and isinstance(sample.get('ts'), (int, float)):
            relative = f' · زمان نسبت به عبور: <bdi dir="ltr">{sample["ts"]-crossing_ts:+.3f} s</bdi>'
        sent = 'ارسال به OCR: ' + '، '.join(VARIANTS.get(s, s) for s in sources) if sources else 'به OCR ارسال نشد'
        attempts = (sample.get('plate_detection') or {}).get('attempts', [])
        box = next((a.get('plate_bbox_in_vehicle') for a in reversed(attempts) if a.get('reason') == 'accepted'), None)
        parts.append(f'<article class="sample" id="frame-{_e(frame)}"><h3>فریم {_e(frame)}{relative}</h3>'
                     f'<p><span class="tag">{_e(sent)}</span> · {_e(REASONS.get(sample.get("reason"), sample.get("reason")))}</p>'
                     '<div class="images">' + pictures.figure(sample.get('vehicle'), 'کراپ خودرو؛ کادر آبی محل پلاک تشخیص‌داده‌شده',
                                                               [(box, '#26a7ff')] if box else [])
                     + pictures.figure(sample.get('raw'), 'پلاک خام از کراپ اصلی خودرو')
                     + pictures.figure(sample.get('geometry'), 'نسخهٔ اصلاح هندسی') + '</div>')
        retained = 'در انتخاب نهایی نگه داشته شد' if sample.get('retained_for_recognition') else 'در انتخاب نهایی نگه داشته نشد'
        parts.append(f'<p>{retained} · اطمینان تشخیص: {_score(sample.get("confidence"))} · امتیاز کیفیت: {_score(sample.get("quality"))}</p>')
        if sample.get('selection_outcome', '').startswith('not_in_final_reserves'):
            parts.append('<p>با معیارهای کیفیت، فاصلهٔ زمانی یا ظرفیت انتخاب نشد؛ عامل منفرد در این آرشیو مشخص نشده است.</p>')
        if sources:
            parts.append(f'<a href="#ocr-frame-{_e(frame)}">مشاهدهٔ ورودی‌ها و خروجی‌های OCR این فریم</a>')
        for attempt in attempts:
            parts.append(f'<p class="muted">مدل {"اصلی" if attempt.get("model") == "primary" else "جایگزین"}: '
                         f'{_e(REASONS.get(attempt.get("reason"), attempt.get("reason")))}</p>')
        details = {'sample': sample, 'selection_decisions': [d for d in decisions if d.get('frame_idx') == frame]}
        parts.append('<details><summary>جزئیات فنی انتخاب و مختصات</summary>' + pictures.figure(sample.get('context'), 'پلاک با ناحیهٔ اطراف')
                     + '<pre>' + _e(json.dumps(details, ensure_ascii=False, indent=2)) + '</pre></details></article>')
    parts.append('</section><section id="ocr"><h2>۳. ورودی‌ها و خروجی‌های OCR</h2>')
    if not inputs:
        parts.append('<p class="missing">ورودی تصویری OCR ثبت نشده است.</p>')
    seen = set()
    sample_frames = {s.get('frame_idx') for s in samples}
    for index, row in enumerate(inputs):
        frame = row.get('frame_idx')
        anchor = f' id="ocr-frame-{_e(frame)}"' if frame not in seen else ''
        seen.add(frame)
        qualifies = bool(row.get('valid')) and float(row.get('confidence', 0)) >= .8
        parts.append(f'<article class="sample"{anchor}><h3>خوانش {index+1} · فریم {_e(frame)} · '
                     f'{_e(VARIANTS.get(row.get("source"), row.get("source")))}</h3><div class="images">'
                     + pictures.figure(row.get('image'), 'تصویر تحویل‌داده‌شده به OCR')
                     + pictures.figure(row.get('model_input'), 'ورودی مدل پس از آماده‌سازی؛ نمایش پیکسل‌ها پیش از نرمال‌سازی عددی') + '</div>'
                     f'<p>خروجی: <strong><bdi>{_e(row.get("text") or "متن خالی")}</bdi></strong> · اطمینان: {_score(row.get("confidence"))}'
                     f' · قالب: {"معتبر" if row.get("valid") else "نامعتبر"}'
                     f' · <span class="{"yes" if qualifies else "no"}">{"رأی معتبر" if qualifies else "بدون رأی معتبر"}</span></p>')
        if not row.get('model_input'):
            parts.append('<p class="muted">تصویر پس از آماده‌سازی داخلی در این آرشیو ثبت نشده؛ از تنظیمات امروز بازسازی نشده است.</p>')
        if frame in sample_frames:
            parts.append(f'<a href="#frame-{_e(frame)}">بازگشت به تصویر خودرو و کراپ پلاک</a>')
        else:
            parts.append('<p class="missing">تصویر خودرو برای این خوانش در محدودهٔ آرشیو موجود نیست.</p>')
        parts.append('</article>')
    runtime = manifest.get('runtime')
    parts.append('</section><section id="settings"><h2>۴. اطلاعات اجرای ثبت‌شده</h2>'
                 f'<p>زمان ایجاد آرشیو — تهران: <bdi dir="ltr">{_e(_stamp(manifest.get("created_at")))}</bdi></p>'
                 f'<p>زمان مشاهدهٔ عبور توسط پردازشگر — تهران: <bdi dir="ltr">{_e(_stamp(scene.get("observed_at")))}</bdi></p>'
                 '<p class="muted">زمان ثبت در سامانه از ردیف تردد گرفته شده است. زمان مشاهدهٔ عبور، زمان پردازش است؛ برای فایل ویدئو، زمان واقعی فیلم‌برداری نیست.</p>')
    if runtime:
        parts.append('<pre>' + _e(json.dumps(runtime, ensure_ascii=False, indent=2)) + '</pre>')
    else:
        parts.append('<p class="missing">نسخهٔ مدل و تنظیمات زمان این اجرا در آرشیو موجود نیست.</p>')
    parts.append('<p class="muted">تصویر خودرو و صحنه JPEG است؛ کراپ‌ها و ورودی OCR با PNG ذخیره می‌شوند. این سند فقط شواهد آرشیوشده را نشان می‌دهد. برای ذخیرهٔ PDF از چاپ مرورگر استفاده کنید.</p></section></main></body></html>')
    return '\n'.join(parts)


class DiagnosticReportService:
    def __init__(self, auth=None, archive_root=None, output_root=None):
        self.auth = auth if auth is not None else auth_service
        self.archive_root = Path(archive_root) if archive_root is not None else None
        self.output_root = Path(output_root) if output_root is not None else DOCUMENT_ROOT

    def _authorize(self, record, session):
        if not self.auth.is_superadmin or self.auth.session_version != session:
            raise PermissionError('فقط سوپر ادمین اجازهٔ مشاهدهٔ گزارش تشخیص دارد')
        if not eligible(record) or type(record.event_id) is not int or record.event_id <= 0:
            raise ValueError('گزارش برای تردد خودروی ناخوانا یا نامطمئن با شناسهٔ ثبت‌شده قابل درخواست است')

    def _roots(self):
        if self.archive_root is not None:
            return [self.archive_root]
        roots = [ARCHIVE_ROOT]
        try:
            config = json.loads((PROJECT_ROOT / 'src/plakino_ui/data/cameras.json').read_text(encoding='utf-8'))
            directory = config.get('crop_diagnostics', {}).get('directory')
            if directory and Path(directory).is_absolute():
                roots.insert(0, Path(directory))
        except (OSError, ValueError, TypeError):
            pass
        return list(dict.fromkeys(p.resolve() for p in roots))

    def prepare(self, record):
        session = self.auth.session_version
        self._authorize(record, session)
        matches = []
        for root in self._roots():
            for path in root.glob('*/manifest.json'):
                if path.resolve().parent.parent != root.resolve():
                    continue
                try:
                    if path.stat().st_size > 8_000_000:
                        continue
                    manifest = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                event = manifest.get('event') or {}
                if (manifest.get('database_event_id') == record.event_id and event.get('camera_id') == record.camera
                        and event.get('direction') == record.direction):
                    matches.append((path.parent, manifest))
        if not matches:
            raise FileNotFoundError('برای این تردد گزارش تشخیصی موجود نیست؛ ممکن است پیش از فعال‌سازی گزارش ثبت شده یا آرشیو آن در دسترس نباشد.')
        if len(matches) != 1:
            raise ValueError('بیش از یک آرشیو برای این شناسه پیدا شد؛ گزارش نامرتبط انتخاب نشد.')
        directory, manifest = matches[0]
        document = render_report(record, manifest, directory)
        self._authorize(record, session)
        self.output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = self.output_root / f'event-{record.event_id}.html'
        temporary = None
        try:
            fd, name = tempfile.mkstemp(prefix='.diagnosis-', suffix='.html', dir=self.output_root)
            temporary = Path(name)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(document)
            self._authorize(record, session)
            temporary.replace(destination)
            return destination
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


diagnostic_report_service = DiagnosticReportService()
