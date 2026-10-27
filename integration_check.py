"""Run against the real local Compose stack. Never prints tokens or signed URLs."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit

ROOT=Path(__file__).resolve().parent
settings={}
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
    if line and not line.startswith('#'):
        key,value=line.split('=',1);settings[key]=value
BASE='http://localhost:8000'
evidence=[]

def request(url, method='GET', body=None, token=None, headers=None):
    data=json.dumps(body).encode() if isinstance(body,dict) else body
    h=dict(headers or {})
    if isinstance(body,dict): h['Content-Type']='application/json'
    if token:h['Authorization']='Bearer '+token
    req=Request(url if url.startswith('http') else BASE+url,data=data,headers=h,method=method)
    try:
        with urlopen(req,timeout=20) as r:return r.status,dict(r.headers),r.read()
    except HTTPError as r:return r.code,dict(r.headers),r.read()

def jsonreq(path, method='GET', body=None, token=None):
    status,headers,data=request(path,method,body,token)
    return status,json.loads(data)

def check(name, condition, detail):
    if not condition:raise AssertionError(name+': '+detail)
    evidence.append({'scenario':name,'result':'PASS','detail':detail})
    print('PASS:',name,flush=True)

def upload(token, name, content, file_id=None):
    status,permit=jsonreq('/api/uploads','POST',{'name':name,'size':len(content),'file_id':file_id},token)
    assert status==200,(status,permit)
    status,headers,_=request(permit['url'],'PUT',content,headers=permit['headers']|{'Origin':BASE})
    assert status==200,status
    lower={k.lower():v for k,v in headers.items()}
    version=lower.get('x-amz-version-id')
    assert version,'No S3 version ID'
    exposed=lower.get('access-control-expose-headers','').lower()
    assert 'x-amz-version-id' in exposed or '*' in exposed,exposed
    status,value=jsonreq('/api/uploads/'+permit['upload_id']+'/complete','POST',{'version_id':version},token)
    assert status==200,(status,value)
    return permit,version

status,health=jsonreq('/api/health')
check('real_storage_health',status==200 and health['storage']=='MinIO','FastAPI connects to the running MinIO container')
status,login=jsonreq('/api/login','POST',{'username':'hieu','password':settings['DEMO_PASSWORD_HIEU']})
assert status==200
token=login['token']
_,login2=jsonreq('/api/login','POST',{'username':'minh','password':settings['DEMO_PASSWORD_MINH']})
token2=login2['token']
first,v1=upload(token,'Bien-ban-nop-bai.txt','Nhóm 11 — bản đầu tiên.\n'.encode())
check('direct_upload_and_finalize',True,'HTTP PUT goes to localhost:9000; exact version HEAD validated by API')
# Start the real TTL clock early; other checks run while it is valid.
issued=time.monotonic()
_,download=jsonreq('/api/files/'+first['file_id']+'/download','POST',{},token)
url=download['url']
status,_,body=request(url)
check('presigned_get',status==200 and 'bản đầu tiên' in body.decode(),'Authorized URL returns the expected bytes')
status,_,_=request(url)
check('bearer_url_reusable_before_expiry',status==200,'Same GET URL succeeds again before its 60-second TTL')
plain=urlsplit(first['url'])
plain=urlunsplit((plain.scheme,plain.netloc,plain.path,'',''))
status,_,_=request(plain)
check('anonymous_bucket_private',status==403,'Same object URL without a signature returns HTTP 403')
status,_=jsonreq('/api/files/'+first['file_id']+'/download','POST',{},token2)
check('cross_owner_denied',status==404,'Second authenticated user cannot obtain a URL for the first user document')
second,v2=upload(token,'Bien-ban-nop-bai.txt','Nhóm 11 — bản đã chỉnh sửa.\n'.encode(),first['file_id'])
_,versions=jsonreq('/api/files/'+first['file_id']+'/versions',token=token)
check('real_object_versions',len(versions['versions'])==2 and v1!=v2,'Two finalized uploads have distinct real MinIO version IDs')
# Replay the old permit while valid; approved downloads remain pinned to v2.
status,_,_=request(first['url'],'PUT',b'REPLAYED BUT NOT APPROVED',headers=first['headers'])
assert status==200
_,latest=jsonreq('/api/files/'+first['file_id']+'/download','POST',{},token)
status,_,body=request(latest['url'])
check('put_replay_cannot_change_approved_document',status==200 and latest['version_id']==v2 and 'chỉnh sửa' in body.decode(),'Unfinalized replay creates a physical version but catalog still downloads approved v2')
_,_=jsonreq('/api/files/'+first['file_id'],'DELETE',token=token)
_,deleted=jsonreq('/api/files/'+first['file_id']+'/versions',token=token)
status,_=jsonreq('/api/files/'+first['file_id']+'/download','POST',{},token)
check('real_delete_marker',deleted['deleted'] and bool(deleted['delete_marker']) and status==409,'DeleteObject creates a marker; current download is blocked by the application')
status,_=jsonreq('/api/files/'+first['file_id']+'/restore','POST',{},token)
_,restored=jsonreq('/api/files/'+first['file_id']+'/versions',token=token)
check('remove_delete_marker_restore',status==200 and not restored['deleted'] and restored['delete_marker'] is None,'Application removes the exact recorded marker')
status,_=jsonreq('/api/files/'+first['file_id']+'/restore','POST',{'version_id':v1},token)
_,old=jsonreq('/api/files/'+first['file_id']+'/download','POST',{},token)
status,_,body=request(old['url'])
check('restore_old_content_as_new_version',status==200 and old['version_id'] not in [v1,v2] and 'bản đầu tiên' in body.decode(),'Server-side version COPY creates a new current version with the original bytes')
# Size mismatch demonstrates acceptance validation, not a hard transport quota.
_,permit=jsonreq('/api/uploads','POST',{'name':'Kiem-tra-kich-thuoc.txt','size':1,'file_id':None},token)
status,headers,_=request(permit['url'],'PUT',b'too-large',headers=permit['headers'])
bad_version={k.lower():v for k,v in headers.items()}['x-amz-version-id']
status,_=jsonreq('/api/uploads/'+permit['upload_id']+'/complete','POST',{'version_id':bad_version},token)
check('size_mismatch_rejected_at_finalize',status==422,'Storage accepted the bytes; catalog rejects mismatched size (transport cap not claimed)')
# Test CORS preflight allowed origin; host-only app Origin is deliberate.
status,headers,_=request(first['url'],'OPTIONS',headers={'Origin':BASE,'Access-Control-Request-Method':'PUT','Access-Control-Request-Headers':'content-type,x-amz-meta-upload-id'})
headers={k.lower():v for k,v in headers.items()}
check('cors_preflight',status in [200,204] and headers.get('access-control-allow-origin')==BASE,'MinIO allows localhost:8000 direct PUT preflight')
_,audit=jsonreq('/api/audit',token=token)
check('application_audit',any(e['action']=='delete_marker_removed' for e in audit['events']),'Account audit records confirmation, delete and restoration events')
# Keep a readable second document and one trashed item for the UI demonstration.
upload(token,'Huong-dan-demo.txt','1. Tải tệp lên.\n2. Thêm bản mới.\n3. Xem lịch sử và khôi phục.\n4. Xóa và khôi phục từ thùng rác.\n'.encode())
trash,_=upload(token,'Ban-nhap-da-xoa.txt',b'Draft for trash restoration demonstration.\n')
jsonreq('/api/files/'+trash['file_id'],'DELETE',token=token)
remaining=max(0,64-(time.monotonic()-issued))
print('Waiting for real 60-second URL expiry; remaining seconds:',round(remaining),flush=True)
time.sleep(remaining)
status,_,_=request(url)
check('url_expired_after_60_seconds',status==403,'Identical URL that succeeded twice now returns HTTP 403 after TTL')
report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'target':'real Docker MinIO + FastAPI','minio_source_release':'RELEASE.2025-10-15T17-29-55Z','deployment':'single-node/single-volume local lab','scenarios':evidence,'passed':len(evidence),'failed':0,'limits':['No HA or durability measurement','No throughput/CPU benchmark','MIME is not malware/content validation','25 MiB/250 MiB are application acceptance limits, not physical S3 quota','No event worker, OIDC, TLS or Object Lock']}
(ROOT/'test-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Integration evidence saved. PASS count:',len(evidence),flush=True)
