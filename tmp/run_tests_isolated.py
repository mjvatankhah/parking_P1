from pathlib import Path
import subprocess,json,re,time
results=[]
for test in sorted(Path('tests').glob('test_*.py')):
 start=time.monotonic()
 try:
  p=subprocess.run(['.venv/bin/python','-m','unittest','discover','-s','tests','-p',test.name],capture_output=True,text=True,timeout=90)
  output=p.stdout+p.stderr;code=p.returncode
 except subprocess.TimeoutExpired as e:
  output='TIMEOUT';code=124
 Path('tmp/'+test.stem+'.log').write_text(output)
 count=re.search(r'Ran (\d+) test',output)
 row=dict(test=test.name,exit_code=code,count=int(count.group(1)) if count else None,seconds=round(time.monotonic()-start,2));results.append(row);print(row,flush=True)
 if code:print(output[-3500:],flush=True)
Path('tmp/test_results_isolated.json').write_text(json.dumps(results,indent=2))
raise SystemExit(any(r['exit_code'] for r in results))
