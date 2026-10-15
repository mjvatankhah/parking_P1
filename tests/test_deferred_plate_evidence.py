import queue
import threading
import unittest
from unittest.mock import Mock,patch
import numpy as np
from computer_vision_v2.ocr_worker.plate_candidates import PlateCandidates,Candidate
from computer_vision_v2.inference.plate_geometry import PreparedPlate
from computer_vision_v2.inference.plate_ocr import PlateReader
from computer_vision_v2.tracking.frame_info import Detection,TrackedFrame
from computer_vision_v2.workers.workers import observation_worker,plate_detection_worker,CameraEnded
from computer_vision_v2.main_v2 import Pipeline

class DeferredEvidenceTests(unittest.TestCase):
 def frame(self,t,others=()):
  return TrackedFrame('cam',round(t*30),t,np.full((100,150,3),100,np.uint8),
                      [Detection(1,(30,20,110,80),2,.9),*others])
 def event(self):return dict(camera_id='cam',track_id=1,class_id=2,ts=0.,direction='entry')
 def test_inference_cannot_block_observation_and_eof_drains_once(self):
  entered=threading.Event();release=threading.Event();results=[]
  reader=Mock()
  def detect(_):entered.set();release.wait(2);return None
  reader.detect_plate.side_effect=detect
  pool=PlateCandidates(reader,deferred=True)
  pool.observe(self.frame(0),[self.event()]);reader.detect_plate.assert_not_called()
  worker=threading.Thread(target=lambda:results.extend(pool.process_pending()))
  worker.start();self.assertTrue(entered.wait(1))
  pool.observe(self.frame(.1))
  self.assertEqual(pool.close(),[])
  self.assertFalse(pool.drained)
  release.set();worker.join(2);self.assertFalse(worker.is_alive())
  while not pool.drained:results.extend(pool.process_pending())
  self.assertEqual(len(results),1);self.assertEqual(reader.detect_plate.call_count,2)
  self.assertEqual(pool.pending_bytes,0);self.assertEqual(pool.close(),[])
 def test_count_byte_budget_and_temporal_coverage(self):
  pool=PlateCandidates(Mock(),deferred=True,sample_capacity=4,max_pending_bytes=200000)
  for i in range(10):pool.observe(self.frame(i*.1))
  pending=pool.tracks[('cam',1)].pending
  self.assertEqual(len(pending),4);self.assertEqual(pending[0].frame_idx,0)
  self.assertEqual(pending[-1].frame_idx,27);self.assertEqual(pool.dropped_samples,6)
  self.assertLessEqual(pool.pending_bytes,200000)
  tiny=PlateCandidates(Mock(),deferred=True,max_pending_bytes=1)
  tiny.observe(self.frame(0));self.assertEqual(tiny.pending_bytes,0)
 def test_margin_is_clipped_and_not_expanded_into_other_car(self):
  reader=Mock();reader.detect_plate.return_value=None
  pool=PlateCandidates(reader)
  pool.observe(self.frame(0));self.assertEqual(reader.detect_plate.call_args.args[0].shape,(84,112,3))
  pool=PlateCandidates(reader)
  other=Detection(2,(120,20,149,80),2,.9)
  pool.observe(self.frame(0,[other]))
  self.assertEqual(reader.detect_plate.call_args_list[-2].args[0].shape,(60,80,3))
 def test_failed_geometry_keeps_multiple_raw_samples(self):
  crop=np.full((25,100,3),100,np.uint8);reader=Mock();reader.detect_plate.return_value=(crop,.9,crop)
  pool=PlateCandidates(reader)
  with patch('computer_vision_v2.ocr_worker.plate_candidates.prepare_plate',return_value=None):
   pool.observe(self.frame(0),[self.event()]);pool.observe(self.frame(.1))
  results=pool.close();self.assertEqual(len(results[0].candidates),2)
 def test_two_cameras_and_tracks_do_not_mix_at_eof(self):
  reader=Mock();reader.detect_plate.return_value=None;pool=PlateCandidates(reader,deferred=True)
  a=self.frame(0);b=self.frame(0);b.camera_id='other'
  pool.observe(a,[self.event()]);other=dict(self.event(),camera_id='other');pool.observe(b,[other])
  self.assertEqual(pool.close('cam'),[])
  results=[]
  for _ in range(3):results.extend(pool.process_pending())
  self.assertEqual([p.event['camera_id'] for p in results],['cam']);self.assertFalse(pool.drained)
  self.assertEqual([p.event['camera_id'] for p in pool.close()],['other']);self.assertTrue(pool.drained)
 def test_real_workers_drain_eof_and_shutdown(self):
  reader=Mock();reader.detect_plate.return_value=None;pool=PlateCandidates(reader,deferred=True)
  fq=queue.Queue();oq=queue.Queue();lines=Mock();lines.update.return_value=[self.event()]
  obs=threading.Thread(target=observation_worker,args=(fq,oq,lines,pool,lambda:True))
  det=threading.Thread(target=plate_detection_worker,args=(pool,oq,lambda:True))
  obs.start();det.start();fq.put(self.frame(0));fq.put(CameraEnded('cam'));fq.put(None)
  obs.join(2);det.join(2)
  self.assertFalse(obs.is_alive());self.assertFalse(det.is_alive());self.assertEqual(oq.qsize(),1)
  self.assertEqual(oq.get()['event']['track_id'],1);self.assertEqual(fq.unfinished_tasks,0)
 def test_overflow_never_discards_eof_control(self):
  q=queue.Queue(maxsize=1);control=CameraEnded('cam');q.put(control)
  Pipeline._dispatch_frame(q,self.frame(1))
  self.assertIs(q.get(),control);q.task_done();self.assertEqual(q.unfinished_tasks,0)

class VariantVoteTests(unittest.TestCase):
 def reader(self,outputs):
  r=PlateReader.__new__(PlateReader);r.labels=['X'];r.ocr=Mock();r.ocr_input='input'
  r.ocr.run.return_value=[None];r._prep_ocr=Mock(return_value=None);r._ctc_decode=Mock(side_effect=outputs);return r
 def candidate(self,frame,prepared=True):
  raw=np.zeros((25,100,3),np.uint8);other=np.ones((25,100,3),np.uint8)
  return Candidate(raw,frame/10,frame,.9,1,prepared=PreparedPlate(other,1) if prepared else None)
 def test_two_variants_and_duplicate_candidate_cannot_create_two_votes(self):
  r=self.reader([('12X34567',.99)]*2);c=self.candidate(1)
  result=r.recognize_candidates([c,c]);self.assertEqual(result['recognition_status'],'uncertain')
  self.assertEqual(len(result['readings']),1);self.assertEqual(r.ocr.run.call_count,2)
 def test_conflicting_variants_abstain(self):
  r=self.reader([('12X34567',.99),('12X34568',.99)]*2)
  result=r.recognize_candidates([self.candidate(1),self.candidate(2)])
  self.assertEqual(result['recognition_status'],'uncertain');self.assertTrue(all(x['conflict'] for x in result['readings']))
 def test_two_against_two_is_not_accepted(self):
  r=self.reader([('12X34567',.99)]*2+[('12X34568',.99)]*2)
  with patch('computer_vision_v2.inference.plate_ocr.prepare_plate',return_value=None):
   result=r.recognize_candidates([self.candidate(i,False) for i in range(4)])
  self.assertEqual(result['recognition_status'],'uncertain')
