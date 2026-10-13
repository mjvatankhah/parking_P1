# بررسی و بهینه‌سازی پلاک‌خوان روی سخت‌افزار موجود

تاریخ گزارش: ۲۰۲۶-۱۰-۱۱. هدف: پژوهش مقایسه‌ای با اولویت سرعت روی دستگاه فعلی، سپس اجرای فقط تغییر دارای شاهد محلی.

## نتیجه

معماری فعلیِ detector سبک + OCR فارسی CRNN مناسب حفظ‌کردن است. از مقایسهٔ منابع، شاهد کافی برای جایگزینی فوری با یک مدل آمادهٔ دیگر به دست نیامد. **یک بهینه‌سازی اجرایی اعمال شد: غیرفعال‌کردن spinning در sessionهای ONNX Runtime، با حفظ تعداد رشتهٔ خودکار.** وزن‌ها، رزولوشن ۶۴۰، threshold، crop، decoder و رویدادهای تردد تغییر نکردند.

در آزمون تأییدی سه‌دوره‌ای، میانهٔ inference تشخیص پلاک ۴۸۵٫۶ → ۲۶۷٫۶ms و OCR برابر ۲۳٫۵ → ۱۹٫۸ms بود. زمان CPU فرایند در حلقهٔ detector حدود ۶۴٪ و OCR حدود ۵۰٪ کمتر شد. این کاهش برای همین آزمایش است؛ سرعت زندهٔ کل برنامه اندازه‌گیری نشده و تضمین real-time نیست. نوسان زمان‌ها قابل توجه است.

[مقایسهٔ تفصیلی ۱۲ گزینه، منابع و نظریهٔ crop/OCR](research.md)؛ [کد تغییر](../../src/computer_vision_v2/inference/plate_ocr.py)؛ [دادهٔ خام آزمون نهایی](spinning_confirmation.json).

## سخت‌افزار و مدل واقعی

محیط در دسترس: Intel Core i5-3470، چهار هسته، AVX و بدون AVX2، Linux در محیط Microsoft virtualization، حدود ۳٫۸GiB RAM. در بررسی اولیه حدود ۱GiB حافظهٔ available و تقریباً تمام swap یک‌گیگابایتی اشغال بود؛ اشغال swap به‌تنهایی ثابت نمی‌کند هنگام هر inference، paging فعال رخ داده است. `/dev/dri` موجود نبود و providerهای ORT فقط CPU و Azure بودند؛ GPU قابل‌استفاده برای این مسیر تأیید نشد.

نسخه‌های نصب‌شده: ORT 1.29.0، OpenVINO 2026.4.0، Ultralytics 8.4.135، PyTorch 2.13.0 و OpenCV 5.0.0.93. مشخصات و hash مدل‌ها در [hardware_models.json](hardware_models.json) ثبت شده‌اند.

| جزء | وضعیت فعلی | اثر بر تصمیم |
|---|---|---|
| تشخیص/رهگیری خودرو | YOLOv8n OpenVINO با ورودی ثابت ۲۵۶×۴۱۶ و ByteTrack؛ optical flow بین detectionها | هزینهٔ پیوستهٔ برنامه؛ تغییر OCR به‌تنهایی این بخش را سریع نمی‌کند |
| detector پلاک | ONNX پویا؛ حدود ۳٫۰۱ میلیون عنصر initializer، ۱۲٫۰۲MiB؛ metadata اندازهٔ ۳۲۰، اجرای برنامه ۶۴۰ | همان وزن در سه اندازه قابل آزمایش است؛ metadata دلیل کافی برای کاهش اندازه نیست |
| fallback پلاک | ONNX ثابت ۶۴۰؛ حدود ۳٫۰۵ میلیون عنصر initializer، ۱۱٫۷۰MiB | فقط شکست بارگذاری مدل اصلی آن را فعال می‌کند؛ نبود detection باعث fallback نمی‌شود |
| OCR فعلی | CRNN؛ حدود ۲٫۶۱ میلیون عنصر initializer، ۹٫۹۷MiB؛ grayscale ۳۲×۱۲۸، خروجی ۳۱×۳۳ | ۳۲ برچسب و blank=32؛ سازگار با فارسی فعلی، decoder عمومی همهٔ OCRها نیست |
| candidate قبلی | YOLOv8m ایرانی؛ حدود ۲۵٫۸۴ میلیون عنصر initializer، ۹۸٫۷۹MiB | حدود ۸٫۶ برابر detector فعال؛ اولویت نامناسب برای سرعت این دستگاه |

تعداد عناصر initializer تقریب اندازهٔ وزن/پارامتر است، نه FLOPs و نه RAM مصرفی runtime. اندازهٔ فایل هم با RSS برابر نیست.

مستند فعلی OpenVINO در فهرست Core به نسل ششم تا چهاردهم اشاره می‌کند؛ این Core نسل سوم است. باوجود اجرای قبلی backend در همین پروژه، پشتیبانی رسمی/سود ارتقای نسخه را نباید از اسم Intel نتیجه گرفت. این بررسی نسخهٔ runtime و backend رهگیری را عوض نکرد. [نیازمندی‌های رسمی](https://docs.openvino.ai/2026/about-openvino/release-notes-openvino/system-requirements.html)

## آزمایش‌ها و محدودیت‌هایشان

ورودی detector: یک crop واقعی خودرو از آزمایش قبلی و پنج فریم تشخیصی از ضبط صفحهٔ دوربین؛ ورودی OCR: تمام ۳۲ عکس پلاک موجود هنگام آزمایش. پنج فریم کامل، نمایندهٔ توزیع crop خودرو در تولید نیستند. نمونه‌ها برچسب ground truth ندارند. هدف این آزمایش، هزینهٔ اجرای وزن ثابت و حفظ خروجی است، نه برآورد دقت یا recall پلاک ایرانی.

برای هر مدل/اندازه/session دو warmup انجام شد. هر دوره session تازه دارد و هر دو مدل، مانند PlateReader، هم‌زمان در حافظه می‌مانند. ترتیب configurationها در دورهٔ دوم معکوس شد. timer زمان `session.run` را می‌گیرد؛ decode ویدیو، پیش‌پردازش، ساخت session، صف‌ها، ذخیرهٔ JPEG و database در latency جدول نیستند. ستون CPU زمان تجمعی threadهای فرایند در حلقه است و علاوه بر inference، مقایسهٔ خروجی/CTC را هم دارد؛ درصد CPU سیستم یا CPU بیکار نیست. OpenCV در اسکریپت benchmark یک‌رشته‌ای است.

آزمون اکتشافی ۳۲۰/۴۱۶/۶۴۰ و threadهای default/1/2/4 در [runtime.json](runtime.json) ذخیره شد. فرایند پس از default دورهٔ سوم با exit143 قطع شد؛ سه configuration باقی‌مانده در [runtime_completion.json](runtime_completion.json) اجرا شدند. [summary.json](summary.json) مجموع آن‌هاست؛ نوبت جداگانه و تغییر بار سیستم علت احتیاط در تفسیر عددهاست.

دو thread در آزمون اکتشافی خوب بود، ولی [آزمون تأییدی مستقل](confirmation.json) آن را به‌عنوان تنظیم سریع‌تر تأیید نکرد: میانهٔ detector از ۵۱۷٫۲ به ۵۸۲٫۵ms رفت، باوجود حدود نصف‌شدن CPU. بنابراین **دو thread پیش‌فرض نشد**.

سپس فقط spinning تغییر کرد؛ `intra_op_num_threads=0` همان انتخاب خودکار تعداد threadهای ORT را حفظ می‌کند. در آزمون نهایی برای هر سیاست، ۱۸ inference detector و ۹۶ inference OCR ثبت شد:

| مدل / سیاست | میانه ms | p95 توصیفی ms | CPU حلقه به‌ازای ورودی ms |
|---|---:|---:|---:|
| detector 640، پیش‌فرض قبلی | 485.6 | 795.8 | 1251.6 |
| detector 640، بدون spinning | 267.6 | 640.4 | 448.7 |
| OCR، پیش‌فرض قبلی | 23.5 | 47.6 | 73.0 |
| OCR، بدون spinning | 19.8 | 38.6 | 36.8 |

میانه‌های هر دورهٔ detector برای baseline: ۷۲۹٫۵، ۵۲۶٫۵، ۳۹۳٫۰ms؛ برای بدون spinning: ۲۴۶٫۳، ۲۲۲٫۴، ۳۷۶٫۸ms. هر سه دوره جهت بهبود یکسان دارند، اما اندازهٔ سود ثابت نیست. p95 از نمونهٔ کوچک محاسبه شده و صدک پایدار تولید محسوب نمی‌شود. raw output در هر اندازه در مقایسه‌های thread دقیقاً برابر بود (max absolute difference = 0).

این رفتار با توضیح ORT سازگار است: spinning می‌تواند latency را در بعضی بارها بهتر کند، اما CPU بیشتری می‌گیرد و sessionهای هم‌زمان می‌توانند رقابت ایجاد کنند. خاموش‌کردن آن انتخاب همیشگی برای هر سخت‌افزار نیست؛ در اینجا با آزمایش انتخاب شد. [مستند thread management](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)

## چرا اندازهٔ ۳۲۰ فعال نشد؟

در probe شمارهٔ چهار، بهترین confidence در اندازه‌های ۶۴۰/۴۱۶/۳۲۰ به‌ترتیب حدود ۰٫۵۴۵/۰٫۲۴۲/۰٫۰۳۵ بود. بنابراین detection بالای threshold=0.35 در اندازه‌های کوچک‌تر از دست رفت. این فریم کامل است و برچسب‌گذاری نشده؛ نتیجه، اثبات افت recall کلی یا صحیح‌بودن آن detection نیست، ولی نشان می‌دهد تغییر اندازه، خروجی را حفظ نمی‌کند. به همین دلیل سرعت بیشتر ۳۲۰ مجوز کافی برای پیش‌فرض‌کردن آن نبود.

تعویض با YOLOv8m هم در [آزمایش قبلی](../plate_model_trial/README.md) روی تنها crop واقعیِ کوچک detection موفقی نداشت و زمان سرد بیشتر بود. نتیجهٔ آن آزمون محدود، دلیلی برای سنگین‌ترکردن برنامه نمی‌دهد.

## تغییری که وارد اپ شد و بررسی آن

`PlateReader()` همچنان همان مدل‌ها و parser را بار می‌کند. `_session` فقط دو گزینهٔ `session.intra_op.allow_spinning=0` و `session.inter_op.allow_spinning=0` را اضافه می‌کند؛ تعداد threadها به‌طور پیش‌فرض خودکار است. حالت اجرا همان sequential پیش‌فرض ORT باقی می‌ماند؛ inter-op در این حالت pool موازی ایجاد نمی‌کند.

برای برگشت به سیاست قبلی در محل ساخت reader از `PlateReader(intra_op_num_threads=None)` استفاده می‌شود. یک عدد مثبت امکان آزمایش thread محدود را دارد؛ default عدد صفر است. تنظیمات هنگام ساخت session اعمال می‌شوند، بنابراین اجرای در حال کار برای دریافت تغییر کد نیاز به راه‌اندازی مجدد دارد؛ دوربین زنده در این کار restart نشد.

[اسکریپت verification](../../scripts/verify_plate_runtime.py) مسیر واقعی `PlateReader.read` شامل preprocessing/NMS/crop/CTC را مقایسه می‌کند؛ فقط ذخیرهٔ JPEG و نام زمان‌دار فایل برای جلوگیری از خروجی جانبی کنترل شده‌اند. ۶ ورودی detector شامل یک نتیجهٔ دارای OCR و پنج نتیجهٔ بدون detection، و ۳۲ crop مستقیم OCR مقایسه می‌شوند. نتیجه در [integration.json](integration.json) است. fixed-shape fallback و رد تنظیم نامعتبر نیز بررسی شدند. این آزمون حفظ رفتار را بررسی می‌کند، نه صحیح‌بودن متن پلاک.

دو تست موجود shutdown pipeline نیز گذشتند؛ syntax فایل‌های تغییرکرده و whitespace diff بررسی شد. database و ثبت تردد زنده در آزمایش‌ها استفاده نشدند. سایر تغییرات قبلی workspace دست‌نخورده باقی ماندند.

## اثر روی هدف اصلی و اولویت بعدی

OCR در این برنامه بعد از crossing و انتخاب crop اجرا می‌شود. زمان پردازش هر فریم بیشتر تابع decode/vehicle detection/tracking است؛ زمان خواندن هر رویداد تابع plate detection + OCR + صف و ذخیره است. افزایش سرعت این دو مدل الزاماً به همان نسبت FPS دوربین را زیاد نمی‌کند.

در [بنچمارک پیشینِ ذخیره‌شدهٔ RTSP](../rtsp_benchmark/openvino_200_frames.json)، ۱۹۹ از ۲۰۰ فریم پردازش‌شده دوباره YOLO اجرا کردند و فقط یک فریم optical flow شد؛ throughput پردازش حدود ۰٫۷۴ FPS بود. کد tracker هنگام فاصله‌افتادن در شمارهٔ فریم detection مجدد می‌کند و capture زنده latest-frame است. این شواهد توضیح می‌دهند چرا `detection_interval=3` الزاماً دو سوم هزینهٔ YOLO را حذف نمی‌کند. این اعداد مربوط به آزمایش قبلی‌اند و baseline/new FPS این تغییر نیستند. دست‌کاری این رفتار بدون بررسی عبورها ممکن است دقت track و رویداد را عوض کند، بنابراین در پژوهش حاضر تغییر نکرد.

اولویت بعدیِ سنجش کیفیت: مجموعهٔ برچسب‌دار از عبورهای همین دوربین و crop با کیفیت اصل تصویر؛ سپس YOLOv9-t 384/416 برای detector و Hezar v2 برای OCR با adapter جدا، در برابر مدل فعلی. برای دقت، exact-match کل پلاک و CER؛ برای سرعت، latency رویداد، FPS رهگیری، dropped frames و صف‌ها باید هم‌زمان ثبت شوند. هیچ دیتاست مستقل شب/روز یا برچسب کافی برای ادعای مدل برتر در این بررسی موجود نبود.

## بازتولید

از ریشهٔ پروژه:

```bash
PYTHONPATH=src .venv/bin/python scripts/benchmark_plate_runtime.py \
  --rounds 3 --threads default 0 --sizes 640 \
  --output /tmp/parking-alpr-confirmation.json

PYTHONPATH=src .venv/bin/python scripts/benchmark_plate_runtime.py \
  --output /tmp/parking-alpr-size-thread-sweep.json

PYTHONPATH=src .venv/bin/python scripts/verify_plate_runtime.py \
  --output /tmp/parking-alpr-integration.json

PYTHONPATH=src .venv/bin/python -m unittest discover \
  -s tests -p 'test_pipeline_shutdown.py' -v
```

در benchmark، `default` سیاست اولیهٔ ORT با spinning است؛ `0` تعداد خودکار بدون spinning و `1/2/4` تعداد مشخص بدون spinning هستند. اسکریپت نخست مستقیماً sessionهای مستقل می‌سازد تا baseline پس از تغییر کد همچنان قابل مقایسه باشد؛ verification از factory واقعی برنامه استفاده می‌کند. benchmark از فایل‌های فعلی نمونه‌برداری می‌کند؛ hash و فهرست ورودی هر اجرا در JSON ثبت می‌شوند تا اضافه‌شدن عکس‌ها پنهان نماند.
