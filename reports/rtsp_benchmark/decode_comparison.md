# RTSP decode comparison

Source: 12-second stream-copy capture from the configured RTSP camera; credentials omitted. HEVC, 1920×1080, declared 30 FPS.

Both methods decoded the first 120 frames to full-resolution BGR24, three runs each, in alternating order. OpenCV used CAP_FFMPEG; direct FFmpeg emitted rawvideo through stdout into Python/NumPy. Measurements include opening, decoding, conversion, and closing. No YOLO, tracking, OCR, or live network waits are included in the timed runs. No hardware decoding was requested.

| Method | Run FPS | Median FPS |
|---|---|---|
| OpenCV / FFmpeg backend | 34.31, 58.47, 57.23 | 57.23 |
| FFmpeg subprocess / rawvideo pipe | 8.07, 32.28, 37.98 | 32.28 |

Direct FFmpeg via a pipe did not improve throughput in this test. Timing variation is substantial, particularly on the first direct-FFmpeg run. These results do not measure live end-to-end application FPS or prove which stage limits production performance. Versions, threading defaults, and pipe copies differ between implementations, so this is a comparison of these concrete paths, not an intrinsic library ranking. The existing OpenCV decoder already uses FFmpeg. Application code and camera configuration were unchanged.
