"""Replay original video pixels with recorded tracking, under real-time input load.

This isolates evidence buffering/detection/OCR. Vehicle tracking is NOT rerun.
No database access. Output is not an accuracy estimate without ground truth.
"""
import argparse,json,time,threading,queue
from pathlib import Path
import cv2
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.tracking.frame_info import Detection,TrackedFrame
from computer_vision_v2.workers.workers import plate_detection_worker

def run(source,output):
 output.mkdir(parents=True,exist_ok=False)
 config=json.loads((source/'config.json').read_text());cam=config['cameras'][0]
 rows=[json.loads(l) for l in (source/'frames.jsonl').read_text().splitlines()]
 cv2.setNumThreads(2);reader=PlateReader();pool=PlateCandidates(reader,deferred=True)
 capture=cv2.VideoCapture(cam['source']);assert capture.isOpened()
 completed=queue.Queue();results=[];errors=[]
 def finish(item):
  started=time.monotonic();result=reader.recognize_candidates(item['candidates']);image=result.pop('image')
  event=item['event'];row=dict(event=event,candidate_frames=[c.frame_idx for c in item['candidates']],result=result,recognition_seconds=time.monotonic()-started)
  if image is not None:cv2.imwrite(str(output/f'track_{event["track_id"]}.png'),image)
  results.append(row);(output/'events.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print('EVENT',event['track_id'],result['recognition_status'],result['plate_text'],flush=True)
 def consume():
  while True:
   item=completed.get()
   if item is None:return
   try:finish(item)
   except Exception as e:errors.append(repr(e))
 worker=threading.Thread(target=plate_detection_worker,args=(pool,completed,lambda:True));ocr=threading.Thread(target=consume)
 worker.start();ocr.start();start=time.monotonic();processed=0;max_bytes=0
 try:
  for row in rows:
   ok,image=capture.read();assert ok,row['frame'];processed+=1
   delay=start+row['ts']-time.monotonic()
   if delay>0:time.sleep(delay)
   frame=TrackedFrame(cam['id'],row['frame'],row['ts'],image,[Detection(**d) for d in row['detections']])
   for p in pool.observe(frame,row['crossings']):completed.put(dict(event=p.event,candidates=p.candidates))
   max_bytes=max(max_bytes,pool.pending_bytes)
   if processed%300==0:print('PROGRESS',processed,len(rows),flush=True)
 finally:
  capture.release()
  for p in pool.close():completed.put(dict(event=p.event,candidates=p.candidates))
  worker.join();completed.put(None);ocr.join()
 summary=dict(processed_frames=processed,expected_frames=len(rows),events=len(results),elapsed_seconds=time.monotonic()-start,
              max_pending_bytes=max_bytes,pending_bytes=pool.pending_bytes,dropped_vehicle_samples=pool.dropped_samples,
              drained=pool.drained,errors=errors,scope='real-time recorded tracking replay; original images; no DB writes')
 (output/'summary.json').write_text(json.dumps(summary,indent=2));print('DONE',summary,flush=True)
 assert not errors and pool.drained and processed==len(rows)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.source,a.output)
