import json
from collections import Counter
from pathlib import Path
out=Path(__file__).resolve().parent
summary=json.loads((out/'summary.json').read_text())
assert summary['complete'], 'Do not report a partial replay as complete'
events=json.loads((out/'events.json').read_text()); counts=Counter(e['result']['recognition_status'] for e in events)
text=f"""# Current-video ALPR diagnosis (2026-10-15)

## Scope and evidence

The attached progress summary describes `InShot_20261012_210725035.mp4`.
The active camera instead uses `InShot_20261015_111930971.mp4`, 1920 x 1080,
1998 frames, approximately 66.5 seconds. Its configured ROI is null.
This report concerns the active video, not the previous four-car recording.

Production tracking, crossing, candidate collection, detector, geometry and OCR
were replayed sequentially. There were no database writes and no production
source/configuration changes for this investigation. EOF finalization is explicit.
This replay isolates recognition from live queue loss; it does not measure live
RTSP performance or reproduce the historical application's exact scheduling.

Processed: {summary['processed_frames']} / {summary['decodable_frames']} decodable frames.
Dropped: {summary['dropped_frames']}. Complete: {summary['complete']}.
Elapsed processing: {summary['elapsed_seconds']:.1f} seconds (excludes setup/census).
Finalized car events: {len(events)}. Status counts: {dict(counts)}.
These are pipeline statuses, not measured accuracy; independent labels for all cars
are unavailable. The source is a montage of several camera scenes, so one gate
line should not be interpreted as a calibrated gate for every scene.

## Confirmed cause 1: automatic text-band extraction destroys readable evidence

Event 1, track 1, frame 4: raw plate 123 x 29 -> prepared 112 x 18.
The prepared image visibly contains bumper/background detail instead of the plate.
Raw OCR gives `48\u062f38467`, confidence 0.996735; prepared OCR gives
`12\u063200`, confidence 0.332320. The second raw crop, frame 7, reads
`48\u062f38467` at 0.987639, but geometry rejects it.
The actual event is uncertain; the same production vote function on the two raw
crops returns read, with the same model and the same acceptance threshold.

Event 2, track 2: all four retained raw crops read `93\u062852733`.
Frame 20: raw 149 x 34 -> prepared 103 x 25; OCR changes from the complete
number (0.996417) to `93\u0628527` (0.976894).
Frame 10: raw 111 x 28 -> prepared 85 x 23; OCR changes from the complete
number (0.969181) to the same incomplete text (0.939628).
The two province digits on the right are visibly removed. Another raw crop,
frame 23, is rejected by geometry despite raw OCR confidence 0.996199.
Only one complete prepared reading survives, so production correctly refuses
to accept it as a final number. Raw-only counterfactual voting returns read.

Code cause: `_prepare_deskew` finds an angle from context edges and chooses the
largest scoring morphology contour. It is not constrained to overlap the
original detector plate rectangle or to retain all plate characters/province
digits. `prepare_plate` receives context without the detected rectangle's
coordinates. The stricter glyph checks in `_rectify_plate` do not validate the
fallback `_prepare_deskew` output.

See `geometry_evidence.jpg`, `cached_ocr_comparison.json`, and
`minimal_ocr_comparison.json`.

## Confirmed cause 2: geometry success is a mandatory OCR gate

`PlateCandidates._sample` stores only one fallback when geometry fails;
`PlateReader.recognize_candidates` tries the same geometry again and skips
candidates for which it still returns None. It never tries their raw detector
crops. Therefore a detectable, OCR-readable plate may be discarded before OCR.
Existing `test_failed_geometry_does_not_run_ocr_and_keeps_review_image` explicitly
asserts this current behavior. A readable raw crop is not a fallback OCR path.

This causes event 1 frame 7 and event 2 frame 23 to be ignored. Event 4 (yellow
taxi) retains one raw fallback but runs no OCR and is reported unread.
For the taxi, raw-only OCR still produces incomplete/unstable text, so fixing
this gate alone does not establish that the taxi is fully readable.

## Additional cause: the vehicle crop can exclude the plate

Event 3, track 11: the visible vehicle is leaving the right edge; inspected
frames 104, 109 and 110 show only part of its side/rear. It has no retained
plate candidates. This example cannot be diagnosed as an OCR decoder error.

Event 4, track 31: the production tracker boxes cut through the lower bumper.
Using the same frame and detector, only the crop margin was varied:

| Frame | Original crop | 10% margin | 20% margin |
|---|---|---|---|
| 334 | no plate detected | detected, score 0.501 | detected, score 0.419 |
| 340 | no plate detected | no plate detected | detected, score 0.363 |

All tested taxi variants still fail geometry. Raw OCR is not a stable complete
number. This proves a crop-recall problem, not a successful taxi recognition fix;
it does not separate vehicle-detector error from tracker smoothing by itself.
See `unread_tracks.jpg` and `vehicle_margin_comparison.json`.

## Event 10: full-frame resolution is not plate resolution

The last-scene uncertain event retains plate crops only 44-62 pixels wide
and 11-17 pixels high in the original pixels. The video frame itself is
1920 x 1080. Raw and transformed OCR are both unstable across these samples;
this case cannot be claimed solved by the first-two-car result. For example,
frame 1482 raw OCR has confidence about 0.965 but emits an incomplete number.
There is no independently established complete plate label for this event.
See `later_events_per_frame_ocr.json` for every retained candidate comparison.

## What these experiments rule out, and what remains open

- Queue dropping is not necessary for the first two failures: both occur in a
  zero-drop sequential replay.
- The five-reading cap is not the cause of those events: only one/three prepared
  readings reach OCR, respectively.
- Replacing OCR is not necessary to recover these two cases: the deployed model
  reads their raw crops repeatedly.
- OCR confidence is not the probability that the full number is correct. The
  truncated frame-20 text has confidence about 0.977 and is still invalid.
- Live production still has a four-frame dropping queue and latest-frame slots;
  those may cause additional losses, but no historical drop counts were supplied.
- No claim is made that every model is correct, or that every vehicle can be
  read from this montage. Detector/crop visibility and OCR remain limiting in
  the taxi and partial vehicle examples.

## Recommended implementation order

1. Retain bounded raw detector crops even if geometry fails. Preserve their frame
   identity and avoid treating variants of one frame as independent votes.
2. Make geometry an optional candidate transformation; anchor its output to the
   detected plate and protect the rightmost province digits. Use a bounded raw
   fallback when transformed evidence is invalid/inconsistent, with conservative
   handling of conflicting full-length results. Keep format validation and
   independent-frame agreement.
3. Add bounded vehicle-crop context, clipped to the original image, and test it
   against simultaneous nearby cars to prevent cross-car plate association.
4. Record per-stage reject reasons (detector miss, clipped crop, geometry reject,
   invalid text, insufficient votes) and queue drops. Current unread/uncertain
   labels conceal very different causes.
5. Validate on both current and earlier images before rollout. The earlier cached
   dataset has 0/74 complete correct raw reads versus 21/38 prepared reads.
   Globally disabling geometry would regress that dataset. These two sample sets
   need conditional handling, not a blanket filter toggle.

## Tight, deterministic reproduction

From the repository root:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python reports/current_video_20261015_diagnosis/replay_cached_ocr.py --minimal --assert-read
# Expected exit 1: current prepared images do not produce the complete number.

OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python reports/current_video_20261015_diagnosis/replay_cached_ocr.py --minimal --raw --assert-read
# Expected exit 0: changing only OCR input to raw gives two complete matching reads.
```

Both commands were executed twice with consistent verdicts, each under one
second in the measured verification loop. See `minimal_reproduction_verdicts.json`.
The minimal comparison uses only frame 10 and 20 of event 2 and the production
OCR decoder, preprocessing and vote function. For the diagnostic raw mode,
raw crops are supplied as prepared images to isolate the input-image variable;
this is an experiment, not a production patch. Cached geometry qualities are not
retained by the full-video tool, so the diagnostic uses equal quality; this
cannot affect the one/three prepared samples in events 1/2 or the two-sample
minimal repro, which are all below the five-reading limit.

Full replay command:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python scripts/replay_video_lossless.py --output reports/current_video_20261015_diagnosis
```

The output directory must not already exist when starting a new full replay.
Exact configuration, events, frame traces and model/source hashes are preserved
alongside this report.

## Full replay event table

| Event | Track | Crossing frame | Final frame | Reason | Candidates | Status | Reported number |
|---|---|---|---|---|---|---|---|
"""
for i,e in enumerate(events,1):
 r=e['result'];text+=f"| {i} | {e['event']['track_id']} | {e['event']['frame_idx']} | {e['finalized_at']} | {e['reason']} | {len(e['candidates'])} | {r['recognition_status']} | {r['plate_text'] or '-'} |\n"
(out/'README.md').write_text(text)
print('WROTE',out/'README.md',dict(counts))
