## مشاهدهٔ کراپ خودرو و پلاک برای عیب‌یابی

مدل تشخیص خودروی برنامه در `models/vehicle/yolo26s.pt` قرار دارد. مدل‌های
`yolov8n.pt`، `yolov8n.onnx` و `yolov8n_openvino_model/` در همان پوشه برای
آزمایش و مقایسهٔ سرعت نگهداری می‌شوند؛ مدل‌های پلاک و OCR در
`src/computer_vision_v2/ocr_worker/models/` هستند. ابزارهای خروجی‌گرفتن و
اندازه‌گیری سرعت در `scripts/` قرار دارند. دستورهای برنامه را از ریشهٔ پروژه
اجرا کنید تا مسیر مدل در `cameras.json` درست پیدا شود.

در `src/computer_vision_v2/debug_plate.py` مقدار `VIDEO_SOURCE` را با مسیر فایل
یا لینک مستقیم ویدیو / RTSP پر کنید و از ریشهٔ پروژه اجرا کنید:

```sh
uv run python -m computer_vision_v2.debug_plate
```

این ابزار همان `CameraTracker` با مدل و فاصلهٔ تشخیص تنظیمات اصلی و همان
`PlateReader` با مدل‌های پیش‌فرض و fallback برنامه را استفاده می‌کند.
چهار بخش نمایش شامل فریم، کراپ خودرو، کراپ پلاک و تصویر ورودی OCR است.
`Space`: توقف/ادامه، `N`: نمونهٔ بعدی (خودروی بعدی یا فریم بعدی)،
`S`: ذخیرهٔ تصویر، `Q` یا `Esc`: خروج.
متن فارسی خروجی OCR، شناسهٔ خودرو، شمارهٔ فریم و امتیاز OCR در نوار زیر
تصاویر نمایش داده می‌شوند و در عکس ذخیره‌شده با `S` نیز دیده می‌شوند.
«تصویر پلاک» برش خروجی مدل تشخیص محل پلاک است؛ «ورودی OCR» همان برش پس
از اصلاح خودکار زاویه و برش نوار نوشته در صورت موفقیت، سپس آماده‌سازی مدل است.
متن فارسی پلاک همچنین در ترمینال و `results.jsonl` در پوشهٔ تاریخ‌دار
`reports/plate_debug` ثبت می‌شود. `no_car` یعنی خودرو تشخیص داده نشده،
`no_plate` یعنی پلاک پیدا نشده، `empty_ocr` یعنی متن خالی است و
`inference_error` همراه جزئیات خطای مدل ثبت می‌شود.
`crop_eligible=false` یعنی کراپ خودرو خالی است.

برای مشاهدهٔ مستقیم عملکرد مدل‌ها، OCR روی هر کراپ خودرو اجرا می‌شود؛ ابزار
منتظر عبور از خط و انتخاب بهترین کراپ نمی‌ماند و در دیتابیس چیزی نمی‌نویسد.
بنابراین گزارش آن به‌تنهایی تأییدکنندهٔ صحت تشخیص عبور و صف‌های برنامه نیست.
تشخیص‌های موقت پلاک روی دیسک نوشته نمی‌شوند. برنامهٔ اصلی فقط تصویر منتخب
رویداد را ذخیره می‌کند. پردازش دیباگ الزاماً با سرعت پخش ویدیو نیست.

## مسیر جدید ثبت تردد

`BestCropSelector` و انتظار ده‌ثانیه‌ای حذف شده‌اند. مشاهده و عبور در یک worker
مرتب انجام می‌شوند؛ برای هر خودرو حداکثر ۱۲ کاندید پلاک و یک نمونهٔ پشتیبان
نگهداری می‌شود. اولین عبور از خط یک رویداد در انتظار می‌سازد. تا وقتی خودرو در
ROI دیده می‌شود، حتی پس از خط، نمونه‌ها جمع می‌شوند. پس از ۰٫۷۵ ثانیه غیبت
در تصویر، رویداد یک‌بار به OCR و دیتابیس می‌رود؛ تغییر کوتاه Track ID فقط با
هم‌پوشانی مکانی و فاصلهٔ زمانی محدود به همان خودرو وصل می‌شود. اصلاح زاویه و
تحلیل هندسی هنگام نمونه‌برداری اجرا می‌شوند؛ فقط کراپ‌های پذیرفته‌شده وارد بافر
اصلی می‌شوند. پس از خروج خودرو، OCR روی حداکثر پنج نمونه بدون شرط حداقل فاصلهٔ زمانی در مرحلهٔ OCR اجرا می‌شود؛
حداقل دو متن کامل یکسان با امتیاز OCR حداقل ۰٫۸ برای وضعیت `read` لازم است.
متن بدون توافق `uncertain` و نبود متن `unread` است. این امتیاز احتمال کالیبره‌شده نیست.
شمارهٔ نامطمئن وارد جدول خودرو یا جلسهٔ ورود/خروج نمی‌شود.

برای تنظیم دوربین روی یک فریم:

```sh
.venv/bin/python -m computer_vision_v2.Line_Manager.select_line_points
```

ابتدا چندضلعی ROI را کلیک کنید و Enter بزنید. برای خط مستقیم دو نقطه انتخاب کنید
و `S` بزنید؛ برای خط L، نقطهٔ سوم را کلیک کنید تا خط خودکار تأیید شود. سپس با
فلش مایل متحرک یک نقطه در سمت داخل پارکینگ انتخاب کنید (`I`: داخل، `O`: خارج).
در حالت خارج، سمت مقابل هر ضلع به‌عنوان داخل در نظر گرفته می‌شود.
`S` تنظیمات کامل را ذخیره می‌کند و `R` انتخاب را از ابتدا شروع می‌کند.
بعد از تغییر تنظیمات، pipeline را دوباره اجرا کنید. بدون ROI، تنظیمات قدیمی
همچنان کل تصویر را پردازش می‌کنند. خطوط باید داخل ROI باشند.
دکمهٔ «محدوده و خط» در فرم ویرایش دوربین همین ابزار را باز می‌کند.
تنظیم اختیاری `plate_sampling` در ریشهٔ JSON شامل `interval` (پیش‌فرض ۰٫۱ ثانیه)،
`capacity` (۱۲)، `near` (۰٫۲۵ ثانیه)، `stale` (۵ ثانیه برای ردگیری بدون عبور)،
`exit_delay` (۰٫۷۵ ثانیه غیبت پیش از نهایی‌کردن)، `reid_gap` (۰٫۵ ثانیه) و
`reid_iou` (۰٫۳۵) است. هر دو طرف خط فرصت تشخیص پلاک دارند؛ خروج خودرو از ROI
زمان پایان جمع‌آوری است. توقف دستی در حالی که خودرو هنوز در ROI دیده می‌شود،
رویداد آن را نهایی نمی‌کند.
نمونه‌برداری پلاک فریم‌های تشخیص مستقیم خودرو را ترجیح می‌دهد؛ اگر تشخیص مستقیم
مدتی در دسترس نباشد، از کادرهای ردیابی نوری هم نمونه می‌گیرد.

پیش از اجرای نسخهٔ جدید روی دیتابیس موجود، migration افزایشی
`src/computer_vision_v2/database/migrations/003_recognition_status.sql` اجرا شود.
این migration رویدادهای قبلی را نگه می‌دارد و وضعیت و جزئیات رأی‌های OCR اضافه می‌کند.

اجرای محدود بدون پنجره، با ذخیرهٔ تصویر هر نمونه:

```sh
uv run python -m computer_vision_v2.debug_plate --video /path/to/video.mp4 --headless --max-frames 10
```

# Plakino real-time benchmark

Run the existing recognition pipeline against `c5.mp4` at its native playback
rate, without a fixed frame-skipping interval:

```sh
python -m computer_vision_v2.main_v2 --benchmark
python -m computer_vision_v2.benchmark --headless --output reports
```

Model loading and detector warmup happen before playback. The display follows
the source timeline independently of inference. A single pending frame is
replaced by newer frames while inference is busy. Source frame indices are
preserved. The player assumes a constant-frame-rate file with valid FPS/count
metadata, as supplied by `c5.mp4` (180 frames, approximately 24 FPS, 7.5 seconds).

After playback the application finishes any in-flight inference and drains the
line, crop and OCR workers, then opens a speed-report dialog. Escape or closing
the playback window produces a report marked `cancelled`. Decode/inference
failures produce an error instead of a successful benchmark report.

Reports and event records are written to `~/PlakinoReports/<timestamp>/` by
default, including plate crops when detected. `--output`, `--video`, and
`--model` accept alternative paths. The packaged executable includes the
existing OpenVINO detector, OCR models, camera line settings, and video.

`processing_fps` is completed detection/tracking and dispatch operations within
the playback window divided by that window's duration. Line/crop/OCR workers
run concurrently with their existing bounded queues. This metric does not mean
every frame underwent OCR: OCR runs on selected crossing-event crops. In-flight
work completed after the video deadline is counted separately. The report also
includes source indices, coverage, scheduling overrun, and pipeline drain time.
Database writes are replaced with local event records for this standalone test;
PostgreSQL is not part of the measurement. Results depend on the target machine.

## Windows x64 package

On the development Windows machine, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
```

The build downloads a private Python environment and CPU dependencies into
`%TEMP%\PlakinoBuild`, builds with PyInstaller, and runs the executable against
the included video before publishing `dist\PlakinoBenchmark-Windows-x64.zip`.
Installed package versions are recorded in `build-packages.txt` in the bundle.
An internet connection is needed for the build, not for playback.
Application modules are frozen into the executable; the installed public
dependencies and matching Python standard library are bundled beside it.
Polars is omitted because this benchmark does not use DataFrame exports and
its default runtime requires CPU instructions absent on the test machine.
Use `-SkipInstall` when rebuilding with the existing Windows build environment.
The build also accepts the matching OpenVINO, OpenCV and Polars Windows wheels
downloaded manually into `%USERPROFILE%\Downloads` (or a directory supplied
with `-WheelDir`). It verifies their SHA-256 hashes before local installation.

Extract the ZIP on the guard's Windows x64 machine and run
`PlakinoBenchmark\PlakinoBenchmark.exe`. Keep the entire extracted folder,
including `_internal`; the EXE alone is not the complete application. No Python
or database installation is required on the target. The console shows startup
and processing activity; the final report appears in a separate dialog.

Only the distribution ZIP is intended for the target machine. It contains no
project `.py` source files. PyInstaller packages Python bytecode, which is not
encryption and can be reverse engineered; this is not absolute source protection.

Run focused tests with `python -m unittest discover -s tests`.
# T_project
# T_project
