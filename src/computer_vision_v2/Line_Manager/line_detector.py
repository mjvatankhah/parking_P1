import math
import time

def _bottom_center(bbox):
    x1 ,y1 ,x2 ,y2 = bbox
    x_center = (float(x1) + float(x2)) / 2.0
    y_center = float(y2)
    return (x_center , y_center)

def _side(line,point):
    (x1 , y1) , (x2 , y2) = line
    px ,py = point
    cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    if cross > 0:
        return 1
    if cross < 0 :
        return -1
    return 0

class LineDetector:
    def __init__(self,camera_id ,line= None ,direction= None , forget_after= 60.0,
                 inside_point=None, coordinate_space='pixels'):
        self.camera_id = camera_id
        if coordinate_space not in ('pixels', 'normalized'):
            raise ValueError(f"Camera {camera_id}: coordinate_space must be pixels or normalized")
        self.coordinate_space = coordinate_space
        self._segments = None
        if line and len(line) > 2:
            # Preserve vertex order: sorting would change the shape of the path.
            self._segments = [
                LineDetector(camera_id, (a, b), direction, forget_after,
                             inside_point, coordinate_space)
                for a, b in zip(line, line[1:])
            ]
            self.line = tuple(tuple(p) for p in line)
            self.forget_after = forget_after
            self._poly_seen = {}
            self._poly_crossed = set()
            for segment in self._segments:
                segment._finite_segment = True
            return
        self._finite_segment = False
        self._positions = {}
        # ترتیب ثابت: چپ به راست؛ برای خط عمودی، بالا به پایین.
        try:
            self.line = tuple(sorted(tuple(p) for p in line)) if line else None
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Camera {camera_id}: invalid line coordinates") from exc
        self.direction = direction
        self.inside_point = None
        self._inside_side = None
        if direction == 'entry_exit' or coordinate_space == 'normalized':
            try:
                valid_line = (
                    self.line is not None
                    and len(self.line) == 2
                    and all(len(p) == 2 and all(math.isfinite(v) for v in p)
                            for p in self.line)
                    and self.line[0] != self.line[1]
                )
                valid_point = (
                    inside_point is not None
                    and len(inside_point) == 2
                    and all(math.isfinite(v) for v in inside_point)
                )
            except (TypeError, ValueError):
                valid_line = valid_point = False
            if not valid_line or (direction == 'entry_exit' and not valid_point):
                raise ValueError(
                    f"Camera {camera_id}: a valid line is required; entry_exit also requires "
                    "inside_point=[x, y] with finite numeric coordinates"
                )
            if coordinate_space == 'normalized':
                if not all(0 <= v <= 1 for p in self.line for v in p):
                    raise ValueError(f"Camera {camera_id}: normalized line coordinates must be between 0 and 1")
                if inside_point is not None and (
                    not valid_point or not all(0 <= v <= 1 for v in inside_point)
                ):
                    raise ValueError(f"Camera {camera_id}: normalized inside_point must be between 0 and 1")
        if direction == 'entry_exit':
            self.inside_point = tuple(inside_point)
            self._inside_side = _side(self.line, self.inside_point)
            if self._inside_side == 0:
                raise ValueError(f"Camera {camera_id}: inside_point must not be on the line")
        self.forget_after = forget_after
        self._state = {}
        self._crossed = set()

    def _cleanup(self,now):
        stale = [t_id for t_id , (_,last_ts) in self._state.items() if now - last_ts > self.forget_after]
        for t_id in stale:
            self._state.pop(t_id)
            self._positions.pop(t_id, None)
            self._crossed.discard(t_id) # برای جلوگیری از خطا در صورت نبود کلید از این متد استفاده شد 

    def update(self,track_frame):
        now = time.monotonic()
        if self._segments is not None:
            for track_id, seen_at in list(self._poly_seen.items()):
                if now - seen_at > self.forget_after:
                    del self._poly_seen[track_id]
                    self._poly_crossed.discard(track_id)
            for detection in track_frame.detections:
                self._poly_seen[detection.track_id] = now
            events = []
            for segment in self._segments:
                for event in segment.update(track_frame):
                    if event['track_id'] not in self._poly_crossed:
                        self._poly_crossed.add(event['track_id'])
                        events.append(event)
            return events
        self._cleanup(now)

        events = []
        width = height = 1
        if self.coordinate_space == 'normalized':
            shape = getattr(track_frame.image, 'shape', ())
            if len(shape) < 2 or shape[0] <= 0 or shape[1] <= 0:
                raise ValueError(f"Camera {self.camera_id}: normalized coordinates require a non-empty frame image")
            height, width = shape[:2]
        for my_track in track_frame.detections:
            t_id = my_track.track_id

            px, py = _bottom_center(my_track.bbox)
            side = _side(self.line, (px / width, py / height))
            point = (px / width, py / height)
            prev_point = self._positions.get(t_id)
            prev = self._state.get(t_id)
            if side == 0:
                # روی خط، آخرین سمت معتبر را حفظ و زمان مشاهده را تازه کن.
                if prev is not None:
                    self._state[t_id] = (prev[0], now)
                continue

            self._state[t_id] = (side , now)
            self._positions[t_id] = point

            if prev is None:
                continue

            prev_side = prev[0]
            if prev_side == 0 or prev_side == side:
                continue

            if t_id in self._crossed: # این ماشین از خط عبور کرده پس نیازی به شمارش مجدد نیست
                continue

            if self._finite_segment and prev_point is not None:
                # The motion must intersect the actual edge, not its extension.
                a, b = self.line
                if _side((prev_point, point), a) * _side((prev_point, point), b) > 0:
                    continue

            # دوربین تک‌نقش، هر عبور را با همان نقش ثبت می‌کند.
            if self.direction in ('entry', 'exit'):
                crossing_direction = self.direction
            elif self.direction == 'entry_exit':
                crossing_direction = 'entry' if side == self._inside_side else 'exit'
            else :
                continue

            self._crossed.add(t_id)
            events.append(self._event(track_frame,my_track,side,crossing_direction))

        return events

    def _event (self,track_frame, my_track, side,crossing_direction):
        return{
            "camera_id" : self.camera_id,
            "track_id" : my_track.track_id,
            "bbox" : tuple(float(i) for i in my_track.bbox),
            "class_id" : my_track.class_id,
            "confidence": float(my_track.confidence),
            "frame_idx":track_frame.frame_idx,
            "ts": track_frame.ts,
            "side":side,    
            "direction":crossing_direction 

        }
class LineDetectorManager:
    def __init__(self, config):
        self.detectors = {}
        for camera in config.get("cameras",[]):
            self.detectors[camera["id"]] = LineDetector(
                camera_id = camera["id"],
                line = camera["line"],
                direction = camera["dir"],
                inside_point = camera.get("inside_point"),
                coordinate_space = camera.get("coordinate_space", "pixels"),

            )


    def get(self,camera_id):
        if camera_id not in self.detectors:
            self.detectors[camera_id] = LineDetector(camera_id)
        return self.detectors[camera_id]

    def update(self,tracked_frame):
        return self.get(tracked_frame.camera_id).update(tracked_frame)


        

            
