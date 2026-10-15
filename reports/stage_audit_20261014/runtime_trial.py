"""Compare the same FP32 plate detector on ORT and OpenVINO, offline."""
import time
import cv2
import numpy as np
import openvino as ov

from audit import save
from computer_vision_v2.inference.plate_ocr import DEFAULT_DETECTOR, _session, _letterbox


def main():
    session = _session(DEFAULT_DETECTOR)
    core = ov.Core()
    start = time.perf_counter()
    compiled = core.compile_model(str(DEFAULT_DETECTOR), 'CPU', {
        'PERFORMANCE_HINT': 'LATENCY', 'INFERENCE_NUM_THREADS': 2,
        'INFERENCE_PRECISION_HINT': 'f32'})
    print('compiled', flush=True)
    report = dict(compile_ms=(time.perf_counter()-start)*1000,
                  precision=str(compiled.get_property('INFERENCE_PRECISION_HINT')), samples=[])
    for frame in (300, 348):
        image = cv2.imread(f'reports/exit_plate_trial/vehicle_{frame}.png')
        boxed, _, _, _ = _letterbox(image)
        blob = np.ascontiguousarray(boxed[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255.
        functions = {'ort':lambda:session.run(None,{session.get_inputs()[0].name:blob})[0],
                     'openvino':lambda:next(iter(compiled(blob).values()))}
        outputs = {k:fn().copy() for k,fn in functions.items()}
        row = dict(frame=frame, max_abs_difference=float(np.max(np.abs(outputs['ort']-outputs['openvino']))), ms={k:[] for k in functions})
        for _ in range(3):
            for name, fn in functions.items():
                start=time.perf_counter();fn()
                row['ms'][name].append((time.perf_counter()-start)*1000)
        row['median_ms']={k:float(np.median(v)) for k,v in row['ms'].items()}
        row['max_score']={k:float(np.squeeze(v)[4].max()) for k,v in outputs.items()}
        report['samples'].append(row)
        save('runtime.json',report)
        print(row,flush=True)


if __name__=='__main__':
    main()
