"""Compare downloaded Hezar OCR against the saved first-exit crop readings.

Requires Hezar in the diagnostic environment. Does not run the pipeline or
write to its database. Uses the model's own preprocessing and decoding.
"""
import argparse
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from hezar.models import Model
from PIL import Image
import torch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path,
                        default=Path('src/computer_vision_v2/ocr_worker/models'))
    parser.add_argument('--crops-zip', type=Path,
                        default=Path('reports/first_exit_ocr_10_crops.zip'))
    parser.add_argument('--output', type=Path,
                        default=Path('reports/hezar_first_exit_comparison.json'))
    args = parser.parse_args()
    torch.set_num_threads(2)
    model = Model.load(str(args.model_dir.resolve()), device='cpu')
    digits = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    rows = []
    with ZipFile(args.crops_zip) as archive:
        baseline = json.loads(archive.read('ocr_results.json'))
        for previous in baseline:
            image = Image.open(BytesIO(archive.read(previous['file']))).convert('RGB')
            prediction = model.predict(image, return_scores=True)[0].to_dict()
            normalized = prediction['text'].translate(digits)
            row = dict(file=previous['file'], frame=previous['frame_idx'],
                       source=previous['source'], old_text=previous['text'],
                       old_confidence=previous['confidence'],
                       hezar=prediction, normalized_text=normalized)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    report = dict(model_directory=str(args.model_dir.resolve()), readings=rows,
                  text_counts=dict(Counter(row['normalized_text'] for row in rows)),
                  note='Hezar scores and existing OCR confidence use different formulas; '
                       'this is a crop comparison, not production acceptance or accuracy validation.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
