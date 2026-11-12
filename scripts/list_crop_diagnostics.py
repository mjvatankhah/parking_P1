"""Find local passage evidence by DB event ID or direction."""
import argparse
import json
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'reports'/'crop_diagnostics')
parser.add_argument('--direction',choices=['entry','exit'])
parser.add_argument('--event',type=int)
parser.add_argument('--limit',type=int,default=10)
args=parser.parse_args()
reports=[]
for path in args.root.glob('*/manifest.json'):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        continue
    if args.direction and data['event'].get('direction')!=args.direction:
        continue
    if args.event is not None and data.get('database_event_id')!=args.event:
        continue
    reports.append((data.get('created_at',''),path,data))
for created,path,data in sorted(reports,reverse=True)[:max(0,args.limit)]:
    print(created,'event=',data.get('database_event_id'),data['event'].get('direction'),
          data['result'].get('recognition_status'),path.parent/'index.html')
if not reports:
    print('No matching diagnostic reports yet.')
