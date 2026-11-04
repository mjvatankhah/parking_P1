"""Isolated first-frame probe; caller kills the process if decoding stalls."""
import json
import sys
from computer_vision_v2.streaming.Source_Base import RTSPSource, VideoSource


def main():
    settings = json.load(sys.stdin)
    source = RTSPSource(settings['source']) if settings['type'] == 'rtsp' else VideoSource(settings['source'])
    try:
        source.connect()
        ok, frame = source.get_frame()
        if not ok or frame is None or not frame.size:
            return 1
        if settings.get('snapshot_path'):
            import cv2
            return 0 if cv2.imwrite(settings['snapshot_path'], frame) else 1
        return 0
    except Exception:
        return 1
    finally:
        source.disconnect()


if __name__ == '__main__':
    sys.exit(main())
