CAR_CLASS_ID = 2

def ocr_worker(ocr_queue, db_queue, plate_reader, running_flag):
    while True:
        item = ocr_queue.get()
        if item is None:  # سیگنال خاموش‌شدن
            break

        event = item["event"]
        best_crop = item['crop']
        camera_id = event['camera_id']
        track_id = event['track_id']
        class_id = event['class_id']

        plate_txt = None
        confidence = float(event.get('confidence', 0.0))
        image_path = None
        results = []

        if class_id == CAR_CLASS_ID and best_crop is not None:
            
            try:
                text, conf, path = plate_reader.read(best_crop['crop'])
            except Exception as e:
                print(f"[ocr_worker] OCR failed {camera_id}/{track_id}: {e}")

            else:
                if path is not None:
                    image_path = path
                if text:
                    plate_txt = text
                    confidence = conf



        db_queue.put(
            {
                "camera_id": camera_id,
                "track_id": track_id,
                "class_id": class_id,
                "direction":event['direction'],
                "plate_text": plate_txt,
                "confidence": confidence,
                "image_path": image_path,
            }
        )
