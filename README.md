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
