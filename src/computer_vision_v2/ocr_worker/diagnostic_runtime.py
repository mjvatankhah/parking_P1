"""Capture reproducible, credential-free settings once per pipeline start."""
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import logging
from pathlib import Path


def _fingerprint(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return {'file': path.name, 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def runtime_by_camera(config, reader, candidates):
    try:
        files = [reader.detector_path]
        if reader._fallback_path:
            files.append(Path(reader._fallback_path))
        files.extend(reader.ocr_model_directory / name for name in
                     ('model.pt', 'model_config.yaml', 'preprocessor/image_processor_config.yaml'))
        vehicle = Path(config['model_path'])
        files.extend(vehicle.glob('*.xml') if vehicle.is_dir() else [vehicle])
        if vehicle.is_dir():
            files.extend(vehicle.glob('*.bin'))
            files.extend(vehicle.glob('*.yaml'))
        models = [_fingerprint(path) for path in dict.fromkeys(files) if path.is_file()]
        packages = {}
        for name in ('hezar', 'ultralytics', 'torch', 'onnxruntime', 'openvino'):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = 'not installed'
        processor = reader.ocr._model.preprocessor.image_processor.config
        preprocessing = {key: getattr(processor, key) for key in
                         ('size', 'mirror', 'gray_scale', 'mean', 'std', 'rescale', 'resample')}
        # Only these camera fields are evidence. Source URLs/passwords are excluded.
        result = {}
        for camera in config.get('cameras', []):
            result[camera['id']] = {
                'camera': {key: camera.get(key) for key in
                           ('id', 'type', 'roi', 'line', 'inside_point', 'coordinate_space', 'dir')},
                'vehicle_input_height_width': [384, 640],
                'detection_interval': config.get('detection_interval', 3),
                'detection_period_seconds': .2,
                'plate_detection_size': reader.det_size,
                'plate_detection_confidence': reader.conf_thr,
                'sampling': {key: getattr(candidates, key) for key in
                             ('interval', 'capacity', 'near', 'stale', 'exit_delay', 'sample_capacity', 'vehicle_margin')
                             if hasattr(candidates, key)},
                'ocr_preprocessing': preprocessing,
                'ocr_vote_rule': {'minimum_confidence': .8, 'minimum_votes': 2, 'unique_winner': True},
                'model_files': models, 'packages': packages,
            }
        # Freeze plain JSON data; later configuration edits must not rewrite history.
        return json.loads(json.dumps(result))
    except Exception:
        logging.getLogger(__name__).exception('Could not snapshot diagnostic runtime settings')
        return {}
