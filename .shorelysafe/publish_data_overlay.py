#!/usr/bin/env python3
"""Refresh approved data files while retaining every currently deployed UI blob."""
import argparse,hashlib,json,os,re,subprocess,urllib.error,urllib.request
from pathlib import Path
DATA_PATHS={
 'flooddashboard':('data/petss_forecast.csv','data/petss_forecast.json','data/petss_meta.json','data/peaks_navd88.json','data/petss_station_debug.txt'),
 'roads-at-risk':('flood_stats.json',),
 'floodmapper':('forecast.json','forecasts.json','observed.json','observedoverflow.json','toptides.json','data/experimental_petss_guidance.json'),
}
def request(site,app,token,endpoint,method='GET',value=None,raw=False):
 url=site.rstrip('/')+'/wp-json/shorelysafe/v1/apps/'+app+'/'+endpoint
 body=value if raw else (json.dumps(value).encode() if value is not None else None)
 req=urllib.request.Request(url,data=body,method=method,headers={'X-ShorelySafe-Token':token,'Content-Type':'application/octet-stream'if raw else'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=120)as r:return json.load(r)
 except urllib.error.HTTPError as e:
  try:d=json.loads(e.read());msg=d.get('message','Request refused');code=d.get('code','unknown')
  except Exception:msg='Request refused';code='unknown'
  # No retries or alternate route around a hosting write gate.
  raise RuntimeError(f'HTTP {e.code} {code}: {msg}')from None

def overlay(base,source,paths,replacements):
 before=base['files'];assert isinstance(before,dict)and'index.html'in before,'Published UI manifest missing'
 after={k:dict(v)for k,v in before.items()};payloads={};changed=[]
 for name in paths:
  p=source/name
  if not p.is_file():continue
  assert not p.is_symlink(),f'Symlink data file: {name}'
  raw=p.read_bytes();assert len(raw)<67108864,f'Data file unexpectedly large: {name}'
  assert not raw.startswith(b'version https://git-lfs.github.com/spec/v1'),f'Git LFS pointer is not data: {name}'
  text=raw.decode('utf-8')
  if p.suffix.lower()=='.json':json.loads(text)
  for old,new in replacements:text=text.replace(old,new)
  data=text.encode();sha=hashlib.sha256(data).hexdigest();entry={'sha256':sha,'size':len(data)}
  if before.get(name)!=entry:changed.append(name);payloads[sha]=data
  after[name]=entry
 for name,entry in before.items():
  if name not in paths:assert after[name]==entry,'UI asset changed'
 assert after['index.html']==before['index.html'],'Index changed'
 return after,payloads,changed

def assert_current(repository,source_sha):
 req=urllib.request.Request('https://api.github.com/repos/'+repository+'/git/ref/heads/main',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
 with urllib.request.urlopen(req,timeout=60)as response:current=json.load(response)['object']['sha']
 assert current==source_sha,'Source changed during publication; refusing to publish an older data snapshot'

def verify_public(url,after,paths):
 checked={}
 for name in ['index.html',*paths]:
  if name not in after:continue
  req=urllib.request.Request(url.rstrip('/')+'/'+name,headers={'Cache-Control':'no-cache'})
  with urllib.request.urlopen(req,timeout=120)as response:raw=response.read()
  sha=hashlib.sha256(raw).hexdigest()
  assert sha==after[name]['sha256'],'Hosted bytes do not match validated publication: '+name
  checked[name]=sha
 return checked

def main():
 p=argparse.ArgumentParser();p.add_argument('--app',required=True);p.add_argument('--site',default='https://cupajoe.live');p.add_argument('--dry-run',action='store_true');args=p.parse_args()
 assert args.site=='https://cupajoe.live','Unexpected publication site'
 root=Path.cwd();apps=json.loads((root/'.shorelysafe/apps.json').read_text());app=next(a for a in apps if a['id']==args.app)
 assert os.environ.get('GITHUB_REPOSITORY',app['repository'])==app['repository'],'Repository/app mismatch'
 from validate_refresh import validate_source,status
 facts=validate_source(root,args.app)
 paths=(*DATA_PATHS[app['product']],'data/refresh_status.json')
 source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
 assert_current(app['repository'],source_sha)
 Path('data-overlay-publication-receipt.json').write_text(json.dumps({'app':args.app,'data_source_commit':source_sha,'source_validation':facts},indent=2)+'\n')
 token=os.environ['SHORELYSAFE_TOKEN'];assert token,'Publisher credential missing'
 state=request(args.site,args.app,token,'state?manifest=1');assert state.get('published')and state.get('manifest'),'No currently published UI; refusing to create a new site'
 base=state['manifest'];replacements=[('https://hondrospj.github.io/'+a['repository'].split('/')[1]+'/',a['path'])for a in apps]
 after,payloads,changed=overlay(base,root,paths,replacements)
 refresh=status(root,args.app,source_sha,facts,DATA_PATHS[app['product']],after)
 raw=(json.dumps(refresh,indent=2)+'\n').encode();sha=hashlib.sha256(raw).hexdigest()
 after['data/refresh_status.json']={'sha256':sha,'size':len(raw)};payloads[sha]=raw
 if 'data/refresh_status.json'not in changed:changed.append('data/refresh_status.json')
 result={'app':args.app,'mode':'current-manifest-data-overlay','data_source_commit':source_sha,'preserved_ui_commit':state.get('commit'),'base_deployment':state.get('deployment'),'file_count':len(after),'preserved_nondatablobs':sum(k not in paths for k in base['files']),'changed_data_files':changed,'index_sha256_before':base['files']['index.html']['sha256'],'index_sha256_after':after['index.html']['sha256'],'dry_run':args.dry_run,'source_validation':facts,'refresh_status':refresh}
 print(json.dumps(result),flush=True)
 if changed and not args.dry_run:
  body={'files':[{'path':k,**v}for k,v in sorted(after.items())],'commit':state.get('commit')or base.get('commit')or source_sha}
  assert_current(app['repository'],source_sha)
  Path('data-overlay-publication-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
  plan=request(args.site,args.app,token,'plan','POST',body)
  for sha in plan['missing']:
   assert sha in payloads,'Server is missing a non-data UI blob; refusing to recreate/replace UI'
   data=payloads[sha];offset=0
   while True:
    chunk=data[offset:offset+524288];r=request(args.site,args.app,token,f'blobs/{sha}?deployment={plan["deployment"]}&offset={offset}','PUT',chunk,True)
    if r.get('complete'):break
    nxt=int(r['offset']);assert offset<nxt<=len(data),'Upload made no progress';offset=nxt
  # Detect concurrent publication before switching the active deployment.
  assert_current(app['repository'],source_sha)
  latest=request(args.site,args.app,token,'state')
  assert latest.get('deployment')==state.get('deployment'),'Concurrent publication changed base; retry against new manifest'
  published=request(args.site,args.app,token,'commit','POST',{'deployment':plan['deployment']})
  verify=request(args.site,args.app,token,'state?manifest=1');assert verify.get('deployment')==plan['deployment']and verify['manifest']['files']==after,'Published manifest verification failed'
  result.update({'published':published.get('published'),'deployment':plan['deployment'],'url':published.get('url'),'ui_blobs_unchanged_verified':True,'hosted_payload_sha256':verify_public(published.get('url')or args.site+app['path'],after,paths)})
 else:result['no_op']=not changed
 print(json.dumps(result),flush=True);Path('data-overlay-publication-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 try:main()
 except Exception as error:
  path=Path('data-overlay-publication-receipt.json')
  result=json.loads(path.read_text())if path.exists()else{}
  result.update({'published':False,'error':str(error)})
  path.write_text(json.dumps(result,indent=2)+'\n')
  raise

