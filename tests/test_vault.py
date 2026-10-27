import copy
import uuid
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.service import Vault, Problem
from app.main import create_app
from app.storage import S3Storage
from urllib.parse import urlsplit, parse_qs


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.last_signed = None
        self.markers = set()
    def ready(self): pass
    def presign_put(self, key, mime, upload_id, ttl):
        self.last_signed = (key, mime, upload_id, ttl)
        return 'http://storage/put', {'Content-Type': mime, 'x-amz-meta-upload-id': upload_id}
    def put(self, key, mime, upload_id, size):
        version = str(uuid.uuid4())
        self.objects[(key, version)] = {'size': size, 'mime': mime, 'upload_id': upload_id, 'version_id': version}
        return version
    def head(self, key, version): return copy.copy(self.objects[(key, version)])
    def presign_get(self, key, version, disposition, ttl):
        self.last_signed = (key, version, disposition, ttl)
        return 'http://storage/get?versionId=' + version
    def delete(self, key):
        marker = str(uuid.uuid4()); self.markers.add((key, marker)); return marker
    def remove_marker(self, key, marker): self.markers.remove((key, marker))
    def copy_version(self, key, version):
        data = self.head(key, version)
        return self.put(key, data['mime'], data['upload_id'], data['size'])


@pytest.fixture
def lab(tmp_path):
    now = [1000.0]
    s = Settings(database=str(tmp_path / 'db.sqlite'), password_hieu='hieu-secret-12345', password_minh='minh-secret-12345')
    store = MemoryS3()
    vault = Vault(s, store, lambda: now[0])
    return vault, store, now


def accepted(lab, owner='hieu', content_size=12, file_id=None, name='Bai nop.txt'):
    vault, store, _ = lab
    upload = vault.allocate(owner, name, content_size, file_id)
    key, mime, nonce, _ = store.last_signed
    version = store.put(key, mime, nonce, content_size)
    vault.complete(owner, upload['upload_id'], version)
    return upload, version, key


def test_authentication_expiry_logout_and_throttle(lab):
    vault, _, now = lab
    result = vault.login('hieu','hieu-secret-12345','test')
    assert vault.authenticate(result['token']) == 'hieu'
    vault.logout(result['token'])
    with pytest.raises(Problem): vault.authenticate(result['token'])
    result = vault.login('hieu','hieu-secret-12345','test')
    now[0] += 3601
    with pytest.raises(Problem): vault.authenticate(result['token'])
    for i in range(8):
        with pytest.raises(Problem) as error: vault.login('hieu','wrong','test')
        assert error.value.status == 401
    with pytest.raises(Problem) as error: vault.login('hieu','hieu-secret-12345','test')
    assert error.value.status == 429


@pytest.mark.parametrize('operation', ['versions','download','delete','restore'])
def test_cross_owner_cannot_read_mutate_or_sign(lab, operation):
    vault, _, _ = lab
    upload, version, _ = accepted(lab)
    with pytest.raises(Problem) as error: getattr(vault, operation)('minh', upload['file_id'])
    assert error.value.status == 404
    assert vault.list_files('minh')['files'] == []
    assert vault.history('minh') == []


def test_cross_owner_cannot_complete_or_add_version(lab):
    vault, _, _ = lab
    upload, version, _ = accepted(lab)
    with pytest.raises(Problem): vault.complete('minh', upload['upload_id'], version)
    with pytest.raises(Problem): vault.allocate('minh','Bai nop.txt',12,upload['file_id'])


@pytest.mark.parametrize('name', ['../secret.txt','a/b.txt','a\\b.txt','x\r\n.txt','code.html','x\u202e.txt',''])
def test_reject_unsafe_names_and_extensions(lab, name):
    with pytest.raises(Problem): lab[0].allocate('hieu', name, 12)


@pytest.mark.parametrize('size', [0, -1, 25*1024*1024+1])
def test_file_size_admission(lab, size):
    with pytest.raises(Problem): lab[0].allocate('hieu','x.txt',size)


def test_unique_generated_keys_avoid_name_collision(lab):
    a, _, key_a = accepted(lab)
    b, _, key_b = accepted(lab)
    assert key_a != key_b and key_a.startswith('users/hieu/')
    assert len(lab[0].list_files('hieu')['files']) == 2


@pytest.mark.parametrize('field,value', [('size',99),('mime','text/html'),('upload_id','wrong')])
def test_finalize_rejects_mismatched_metadata(lab, field, value):
    vault, store, _ = lab
    up = vault.allocate('hieu','x.txt',12)
    key,mime,nonce,_ = store.last_signed
    version=store.put(key,mime,nonce,12)
    store.objects[(key,version)][field]=value
    with pytest.raises(Problem) as error: vault.complete('hieu',up['upload_id'],version)
    assert error.value.status == 422
    assert vault.list_files('hieu')['files'] == []


def test_finalize_expiry_and_idempotency(lab):
    vault, store, now=lab
    up,version,key=accepted(lab)
    assert vault.complete('hieu',up['upload_id'],version)['version_id']==version
    with pytest.raises(Problem): vault.complete('hieu',up['upload_id'],'other-version')
    pending=vault.allocate('hieu','x.txt',12)
    key,mime,nonce,_=store.last_signed
    ver=store.put(key,mime,nonce,12)
    now[0]+=181
    with pytest.raises(Problem) as error: vault.complete('hieu',pending['upload_id'],ver)
    assert error.value.status==410


def test_replayed_put_does_not_replace_approved_version(lab):
    vault, store, _=lab
    up,version,key=accepted(lab)
    # Presigned PUT is reusable while valid. A replay is a physical S3 version only.
    replay=store.put(key,'text/plain',up['upload_id'],99)
    assert replay != version
    assert vault.download('hieu',up['file_id'])['version_id']==version
    assert len(vault.versions('hieu',up['file_id'])['versions'])==1
    with pytest.raises(Problem): vault.download('hieu',up['file_id'],replay)


def test_versions_delete_marker_and_restore(lab):
    vault, store, now=lab
    first,v1,key=accepted(lab)
    now[0]+=1
    _,v2,_=accepted(lab,file_id=first['file_id'],content_size=15)
    assert len(vault.versions('hieu',first['file_id'])['versions'])==2
    vault.delete('hieu',first['file_id'])
    assert len(store.markers)==1
    with pytest.raises(Problem): vault.download('hieu',first['file_id'])
    assert vault.download('hieu',first['file_id'],v1)['version_id']==v1
    vault.restore('hieu',first['file_id'])
    assert not store.markers
    assert vault.download('hieu',first['file_id'])['version_id']==v2
    vault.restore('hieu',first['file_id'],v1)
    new=vault.download('hieu',first['file_id'])['version_id']
    assert new not in (v1,v2)
    assert len(vault.versions('hieu',first['file_id'])['versions'])==3


def test_quota_reserves_pending_uploads(lab):
    vault, _, _=lab
    vault.settings.quota_bytes=20
    vault.allocate('hieu','x.txt',12)
    with pytest.raises(Problem) as error: vault.allocate('hieu','y.txt',12)
    assert error.value.status==409


def test_api_routes_require_bearer_and_reject_extra_fields(lab):
    client=TestClient(create_app(lab[0]))
    assert client.get('/api/files').status_code==401
    result=client.post('/api/login',json={'username':'hieu','password':'hieu-secret-12345'})
    assert result.status_code==200
    headers={'Authorization':'Bearer '+result.json()['token']}
    assert client.get('/api/files',headers=headers).status_code==200
    assert client.post('/api/uploads',headers=headers,json={'name':'x.txt','size':12,'owner':'minh'}).status_code==422
    assert client.post('/api/uploads',headers=headers,json={'name':'x.txt','size':'12'}).status_code==422
    assert client.get('/').status_code==200
    assert 'frame-ancestors' in client.get('/').headers['content-security-policy']


def test_real_boto3_signature_contains_method_scope_and_version():
    settings=Settings(access_key='lab-access-key',secret_key='lab-secret-key',public_endpoint='http://localhost:9000')
    storage=S3Storage(settings)
    url,headers=storage.presign_put('users/hieu/unique','text/plain','nonce-123',180)
    query=parse_qs(urlsplit(url).query)
    assert query['X-Amz-Expires']==['180']
    assert 'content-type' in query['X-Amz-SignedHeaders'][0]
    assert 'x-amz-meta-upload-id' in query['X-Amz-SignedHeaders'][0]
    assert settings.secret_key not in url
    url=storage.presign_get('users/hieu/unique','version-1','attachment',60)
    assert parse_qs(urlsplit(url).query)['versionId']==['version-1']


def test_restore_respects_pending_upload_reservations(lab):
    vault, _, _ = lab
    up, version, _ = accepted(lab, content_size=12)
    vault.settings.quota_bytes = 30
    vault.allocate('hieu', 'pending.txt', 12)
    with pytest.raises(Problem) as error:
        vault.restore('hieu', up['file_id'], version)
    assert error.value.status == 409
