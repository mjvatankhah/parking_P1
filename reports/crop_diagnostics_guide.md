# Passage crop diagnostics

Enabled by default when a new `Pipeline` starts. This records evidence only; it does not change crop ranking, OCR, voting or acceptance thresholds. Both entry and exit events are captured, including unread events with no accepted plate candidate.

Reports live in `reports/crop_diagnostics/<diagnostic-id>/index.html`. Open the HTML locally; no server or external assets are needed. `manifest.json` contains the database event ID (added after commit), camera, direction, track ID, crossing frame, crop coordinates, sample times, detection rejection reason, raw and geometry scores, reserve decisions, final reserve membership, and exact OCR readings and input images.

Compare these in order:

1. Full crossing frame and detector/expanded vehicle boxes in metadata; check whether the plate falls outside the vehicle crop.
2. Sampled vehicle crop against its plate/context crop; inspect `plate_bbox_in_vehicle` and `used_implausible_fallback`.
3. Raw plate against geometry output. Raw/context/geometry and exact OCR inputs are lossless PNG. Vehicle/scene snapshots are JPEG quality 90.
4. `selection_decisions`, `selection_groups`, and each sample's `ocr_sources`: was a readable sample excluded from final reserves, or retained but not sent to OCR?
5. Exact OCR input gallery: does geometry remove characters or improve them? Do raw/geometry votes disagree?

Only sampled frames are observed. The first 80 processed samples have image evidence; later omissions are counted. Up to 600 reserve decisions are retained. Each active track has a 12 MB image budget, of which 2 MB is reserved for exact OCR images. `omitted_samples`, `omitted_images`, and `dropped_pending` distinguish missing evidence from failed detection. A missing geometry image may mean preparation failed or the image budget was exhausted; consult the metadata. A single final preview is not sufficient to judge all candidates.

The archive stops accepting new reports at approximately 512 MB and logs a warning; it never automatically deletes existing evidence. Move old event directories elsewhere to resume recording. Disk/encoding/report failures are logged and do not prevent normal event persistence. An unlinked report (`database_event_id: null`) may indicate a pending/failed DB insert or a report-link failure; match its preview path in `result.image_path` against the event table.

Optional top-level camera configuration (restart required):

```json
"crop_diagnostics": {"enabled": true, "directory": "/absolute/path/to/reports"}
```

Set `enabled` to false to turn diagnostics off. Generated reports are excluded from git. Existing historical events cannot recover previously discarded crops.

List recent reports without opening their images:

```bash
.venv/bin/python scripts/list_crop_diagnostics.py --direction exit --limit 10
```
