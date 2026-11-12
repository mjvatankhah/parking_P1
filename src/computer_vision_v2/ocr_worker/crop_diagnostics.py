"""Bounded, best-effort evidence for a passage; never changes recognition votes."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import html
import json
import logging

import cv2

logger = logging.getLogger(__name__)
DEFAULT_ROOT = Path(__file__).resolve().parents[3] / 'reports' / 'crop_diagnostics'


def guarded(fn):
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception('Crop diagnostics failed in %s; recognition continues', fn.__name__)
    return call


class EvidenceTrace:
    def __init__(self, root=None, max_samples=80, max_bytes=12_000_000):
        self.root = Path(root) if root else DEFAULT_ROOT
        self.token = uuid4().hex
        self.max_samples = max_samples
        self.max_bytes = max_bytes
        self.rows = []
        self.images = {}
        self.bytes = 0
        self.omitted_samples = 0
        self.omitted_images = 0
        self.scene = None
        self.ocr_rows = []
        self.dropped_pending = 0
        self.decisions = []

    def _image(self, name, image, *, jpeg=False):
        if image is None or not image.size:
            return None
        extension = '.jpg' if jpeg else '.png'
        ok, data = cv2.imencode(extension, image, [cv2.IMWRITE_JPEG_QUALITY, 90] if jpeg else [])
        if not ok:
            raise OSError('Could not encode diagnostic image')
        limit = self.max_bytes if name.startswith("ocr-") else max(0, self.max_bytes - 2_000_000)
        if self.bytes + data.nbytes > limit:
            self.omitted_images += 1
            return None
        name += extension
        self.images[name] = data.tobytes()
        self.bytes += data.nbytes
        return name

    @guarded
    def crossing(self, frame, event):
        if self.scene is not None:
            return
        self.scene = {'frame_idx': frame.frame_idx, 'shape': list(frame.image.shape),
                      'bbox': event.get('bbox'),
                      'detections': [{'track_id': d.track_id, 'bbox': list(d.bbox),
                                      'class_id': d.class_id} for d in frame.detections],
                      'image': self._image('crossing-scene', frame.image, jpeg=True)}

    @guarded
    def sample(self, sample, candidate, detection_details=None, reason=None):
        if len(self.rows) >= self.max_samples:
            self.omitted_samples += 1
            return
        prefix = f'sample-{len(self.rows):03d}-frame-{sample.frame_idx}'
        row = {'frame_idx': sample.frame_idx, 'ts': sample.ts,
               'vehicle_bbox': sample.vehicle_bbox, 'detector_bbox': sample.detector_bbox,
               'frame_shape': sample.frame_shape, 'predicted': sample.predicted,
               'vehicle': self._image(prefix+'-vehicle', sample.image, jpeg=True),
               'plate_detection': detection_details, 'reason': reason,
               'raw': None, 'context': None, 'geometry': None}
        if candidate is not None:
            row.update(raw=self._image(prefix+'-raw', candidate.crop),
                       context=self._image(prefix+'-context', candidate.context),
                       raw_shape=list(candidate.crop.shape),
                       confidence=candidate.confidence, quality=candidate.quality,
                       geometry_quality=getattr(candidate.prepared, 'quality', None),
                       geometry=self._image(prefix+'-geometry', candidate.prepared.image)
                       if candidate.prepared is not None else None,
                       reason='candidate' if candidate.prepared is not None else 'geometry_unavailable')
        self.rows.append(row)

    @guarded
    def decision(self, frame_idx, branch, outcome):
        if len(self.decisions) < 600:
            self.decisions.append({"frame_idx": frame_idx, "branch": branch, "outcome": outcome})

    @guarded
    def ocr(self, reading, image):
        # Exact images used by OCR, including any geometry recomputed at recognition.
        self.ocr_rows.append({**reading, 'image': self._image(
            f'ocr-{len(self.ocr_rows):02d}-{reading["source"]}-{reading["frame_idx"]}', image)})

    @guarded
    def save(self, event, result, candidates):
        # Stop collecting new archives at 512 MB; never silently delete evidence.
        used = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file()) if self.root.exists() else 0
        if used + self.bytes + 1_000_000 > 512_000_000:
            logger.warning("Crop diagnostics archive is full (%s); event is still saved", self.root)
            return None
        directory = self.root / self.token
        directory.mkdir(parents=True, exist_ok=False)
        for name, data in self.images.items():
            (directory / name).write_bytes(data)
        selected = {(r['frame_idx'], r['source']) for r in self.ocr_rows}
        retained = {c.frame_idx for c in candidates}
        groups = getattr(candidates, 'selection_groups', {})
        for row in self.rows:
            frame = row['frame_idx']
            row['retained_for_recognition'] = frame in retained
            row['ocr_sources'] = [source for source in ('raw','geometry') if (frame,source) in selected]
            row['final_reserves'] = {source: [name for name, ids in reserves.items() if frame in ids]
                                     for source, reserves in groups.items()}
            if row['reason'] in ('candidate', 'geometry_unavailable') and frame not in retained:
                row['selection_outcome'] = 'not_in_final_reserves: quality/time_spacing/capacity'
            else:
                row['selection_outcome'] = 'sent_to_ocr' if row['ocr_sources'] else 'not_sent_to_ocr'
        manifest = {'version': 1, 'diagnostic_id': self.token,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'database_event_id': None, 'event': event,
                    'result': {k: v for k,v in result.items() if k != 'image'},
                    'crossing': self.scene, 'samples': self.rows, 'ocr_inputs': self.ocr_rows,
                    'selection_groups': groups, 'selection_decisions': self.decisions,
                    'dropped_pending': self.dropped_pending,
                    'omitted_samples': self.omitted_samples, 'omitted_images': self.omitted_images,
                    'limits': {'max_samples': self.max_samples, 'max_bytes': self.max_bytes},
                    'notes': 'Sampled frames only. Vehicle/scene JPEG; raw/context/geometry lossless PNG. Missing evidence is not proof of absence.'}
        _write_report(directory, manifest)
        return str(directory)


def _write_report(directory, manifest):
    def escaped(value):
        return html.escape(json.dumps(value, ensure_ascii=False, default=str, indent=2))
    def picture(name, label):
        return f'<figure><figcaption>{html.escape(label)}</figcaption><a href="{name}"><img src="{name}"></a></figure>' if name else ''
    blocks = ['<!doctype html><meta charset="utf-8"><title>Crop diagnostics</title>',
              '<style>body{font:16px sans-serif;background:#171a20;color:#eee;margin:24px}section{border-top:1px solid #777;padding:20px 0}.images{display:flex;flex-wrap:wrap;gap:16px}figure{margin:0}img{max-width:480px;max-height:350px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#9dd4ff}</style>',
              '<h1>Passage crop evidence</h1><pre>'+escaped({k:v for k,v in manifest.items() if k not in ('samples','ocr_inputs')})+'</pre>']
    blocks.append(picture((manifest.get('crossing') or {}).get('image'), 'Full crossing frame — boxes in metadata'))
    blocks.append('<h2>Exact OCR inputs and readings</h2>')
    for row in manifest['ocr_inputs']:
        blocks.append('<section>'+picture(row.get('image'), f"Frame {row['frame_idx']} / {row['source']}")+'<pre>'+escaped(row)+'</pre></section>')
    blocks.append('<h2>Sampled vehicles, raw plates and geometry</h2>')
    for row in manifest['samples']:
        blocks.append('<section><div class="images">'+''.join(picture(row.get(k),k) for k in ('vehicle','raw','context','geometry'))+'</div><pre>'+escaped(row)+'</pre></section>')
    for name, content in [('manifest.json',json.dumps(manifest, ensure_ascii=False, default=str, indent=2)), ('index.html','\n'.join(blocks))]:
        temporary = directory / (name+'.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(directory/name)


@guarded
def link_event(directory, event_id):
    """Called only after DB commit. Failure must not roll back a saved passage."""
    if not directory:
        return
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    manifest['database_event_id'] = event_id
    _write_report(directory, manifest)
