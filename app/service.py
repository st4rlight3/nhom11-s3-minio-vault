"""Application policy. Every public operation receives an authenticated owner ID.

Only validated, explicit S3 version IDs enter the application catalog. A replayed
PUT URL can create an extra S3 version, but cannot alter an approved document.
"""
from contextlib import contextmanager
import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import quote


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Vault:
    USERS = {"hieu": "Nguyễn Minh Hiếu", "minh": "Nguyễn Đăng Minh"}
    MIME = {".pdf": "application/pdf", ".txt": "text/plain",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".zip": "application/zip", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

    def __init__(self, settings, storage, clock=time.time):
        self.settings, self.storage, self.clock = settings, storage, clock
        self.lock = threading.RLock()
        self.sessions, self.failures = {}, {}
        Path(settings.database).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, owner TEXT NOT NULL,
              name TEXT NOT NULL, object_key TEXT NOT NULL UNIQUE, created REAL NOT NULL,
              active_version TEXT, deleted INTEGER NOT NULL DEFAULT 0, marker TEXT);
            CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY, file_id TEXT NOT NULL,
              owner TEXT NOT NULL, size INTEGER NOT NULL, mime TEXT NOT NULL, expires REAL NOT NULL,
              state TEXT NOT NULL DEFAULT 'pending', version_id TEXT);
            CREATE TABLE IF NOT EXISTS versions (file_id TEXT NOT NULL, version_id TEXT NOT NULL,
              size INTEGER NOT NULL, mime TEXT NOT NULL, created REAL NOT NULL,
              PRIMARY KEY(file_id, version_id));
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT,
              owner TEXT NOT NULL, action TEXT NOT NULL, file_id TEXT, detail TEXT NOT NULL, at REAL NOT NULL);
            """)

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.settings.database, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def audit(self, c, owner, action, file_id=None, detail=""):
        c.execute("INSERT INTO audit(owner,action,file_id,detail,at) VALUES(?,?,?,?,?)",
                  (owner, action, file_id, detail, self.clock()))

    def login(self, username, password, client_ip):
        with self.lock:
            now = self.clock()
            self.failures = {k: [t for t in v if t > now - 60] for k, v in self.failures.items()
                             if any(t > now - 60 for t in v)}
            if len(self.failures.get(client_ip, [])) >= 8:
                raise Problem(429, "Đăng nhập quá nhiều lần. Vui lòng đợi một phút.")
            expected = {"hieu": self.settings.password_hieu, "minh": self.settings.password_minh}.get(username, "invalid-password")
            if username not in self.USERS or not hmac.compare_digest(password.encode(), expected.encode()):
                self.failures.setdefault(client_ip, []).append(now)
                raise Problem(401, "Tài khoản hoặc mật khẩu chưa đúng.")
            self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}
            token = secrets.token_urlsafe(32)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (username, now + 3600)
            with self.db() as c:
                self.audit(c, username, "login")
            return {"token": token, "expires_in": 3600, "user": {"id": username, "name": self.USERS[username]}}

    def authenticate(self, token):
        session = self.sessions.get(hashlib.sha256(token.encode()).hexdigest())
        if not session or session[1] <= self.clock():
            raise Problem(401, "Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.")
        return session[0]

    def logout(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    @staticmethod
    def owned(c, owner, file_id):
        row = c.execute("SELECT * FROM files WHERE id=? AND owner=?", (file_id, owner)).fetchone()
        if row is None:
            raise Problem(404, "Không tìm thấy tài liệu.")
        return row

    @classmethod
    def filename(cls, name):
        name = unicodedata.normalize("NFC", name.strip())
        if not 1 <= len(name) <= 160 or any(x in name for x in ["/", "\\", "\r", "\n", "\0"]) or name in [".", ".."]:
            raise Problem(422, "Tên tệp không hợp lệ (tối đa 160 ký tự, không chứa đường dẫn).")
        if any(unicodedata.category(ch).startswith("C") for ch in name):
            raise Problem(422, "Tên tệp chứa ký tự điều khiển.")
        ext = Path(name).suffix.lower()
        if ext not in cls.MIME:
            raise Problem(422, "Chỉ nhận PDF, DOCX, PPTX, TXT, ZIP, PNG và JPG.")
        return name, cls.MIME[ext]

    def allocate(self, owner, name, size, file_id=None):
        name, mime = self.filename(name)
        if not 1 <= size <= self.settings.max_file_bytes:
            raise Problem(422, "Dung lượng hợp lệ: 1 byte đến 25 MiB.")
        with self.lock, self.db() as c:
            now = self.clock()
            c.execute("UPDATE uploads SET state='expired' WHERE state='pending' AND expires<?", (now,))
            pending = c.execute("SELECT COUNT(*) AS n,COALESCE(SUM(size),0) AS bytes FROM uploads WHERE owner=? AND state='pending'", (owner,)).fetchone()
            used = c.execute("SELECT COALESCE(SUM(v.size),0) AS bytes FROM versions v JOIN files f ON f.id=v.file_id WHERE f.owner=?", (owner,)).fetchone()["bytes"]
            if pending["n"] >= 10 or used + pending["bytes"] + size > self.settings.quota_bytes:
                raise Problem(409, "Đã đạt giới hạn phiên tải hoặc hạn mức 250 MiB lịch sử mỗi tài khoản.")
            if file_id:
                file = self.owned(c, owner, file_id)
                if file["deleted"]:
                    raise Problem(409, "Khôi phục tài liệu trước khi thêm phiên bản.")
                if Path(name).suffix.lower() != Path(file["name"]).suffix.lower():
                    raise Problem(422, "Phiên bản mới phải cùng định dạng với tài liệu.")
                key = file["object_key"]
            else:
                file_id = str(uuid.uuid4())
                key = f"users/{owner}/{file_id}"
                c.execute("INSERT INTO files(id,owner,name,object_key,created) VALUES(?,?,?,?,?)", (file_id, owner, name, key, now))
            upload_id = str(uuid.uuid4())
            url, headers = self.storage.presign_put(key, mime, upload_id, self.settings.upload_ttl)
            c.execute("INSERT INTO uploads(id,file_id,owner,size,mime,expires) VALUES(?,?,?,?,?,?)", (upload_id, file_id, owner, size, mime, now + self.settings.upload_ttl))
            self.audit(c, owner, "upload_authorized", file_id, f"{size} bytes")
            return {"upload_id": upload_id, "file_id": file_id, "url": url, "headers": headers,
                    "expires_in": self.settings.upload_ttl}

    def complete(self, owner, upload_id, version_id):
        if not version_id or len(version_id) > 256 or version_id == "null":
            raise Problem(422, "Thiếu version ID hợp lệ từ phản hồi PUT của MinIO.")
        with self.lock, self.db() as c:
            upload = c.execute("SELECT * FROM uploads WHERE id=? AND owner=?", (upload_id, owner)).fetchone()
            if not upload:
                raise Problem(404, "Không tìm thấy phiên tải.")
            if upload["state"] == "complete":
                if upload["version_id"] != version_id:
                    raise Problem(409, "Phiên tải đã hoàn tất với phiên bản khác.")
                return {"file_id": upload["file_id"], "version_id": version_id}
            if upload["state"] != "pending" or upload["expires"] < self.clock():
                raise Problem(410, "Phiên tải đã hết hạn. Hãy cấp lại URL và thử lại.")
            file = self.owned(c, owner, upload["file_id"])
            if file["deleted"]:
                raise Problem(409, "Tài liệu đã bị xóa trong lúc tải.")
            obj = self.storage.head(file["object_key"], version_id)
            if obj != {"size": upload["size"], "mime": upload["mime"], "upload_id": upload_id, "version_id": version_id}:
                raise Problem(422, "Dữ liệu trên kho không khớp dung lượng, loại hoặc mã phiên đã cấp.")
            c.execute("INSERT INTO versions VALUES(?,?,?,?,?)", (file["id"], version_id, upload["size"], upload["mime"], self.clock()))
            c.execute("UPDATE files SET active_version=? WHERE id=?", (version_id, file["id"]))
            c.execute("UPDATE uploads SET state='complete',version_id=? WHERE id=?", (version_id, upload_id))
            self.audit(c, owner, "upload_completed", file["id"], version_id)
            return {"file_id": file["id"], "version_id": version_id}

    def list_files(self, owner):
        with self.db() as c:
            rows = c.execute("""SELECT f.id,f.name,f.created,f.deleted,f.active_version,v.size,
              (SELECT COUNT(*) FROM versions vv WHERE vv.file_id=f.id) AS version_count
              FROM files f JOIN versions v ON v.file_id=f.id AND v.version_id=f.active_version
              WHERE f.owner=? ORDER BY f.created DESC""", (owner,)).fetchall()
            used = c.execute("SELECT COALESCE(SUM(v.size),0) FROM versions v JOIN files f ON f.id=v.file_id WHERE f.owner=?", (owner,)).fetchone()[0]
            return {"files": [dict(x) for x in rows], "used_bytes": used, "quota_bytes": self.settings.quota_bytes}

    def versions(self, owner, file_id):
        with self.db() as c:
            file = self.owned(c, owner, file_id)
            rows = c.execute("SELECT * FROM versions WHERE file_id=? ORDER BY created DESC", (file_id,)).fetchall()
            return {"versions": [dict(x) | {"active": x["version_id"] == file["active_version"]} for x in rows],
                    "deleted": bool(file["deleted"]), "delete_marker": file["marker"]}

    def download(self, owner, file_id, version_id=None):
        with self.db() as c:
            file = self.owned(c, owner, file_id)
            if not version_id:
                if file["deleted"]:
                    raise Problem(409, "Tài liệu đang ở thùng rác.")
                version_id = file["active_version"]
            if not c.execute("SELECT 1 FROM versions WHERE file_id=? AND version_id=?", (file_id, version_id)).fetchone():
                raise Problem(404, "Không tìm thấy phiên bản đã xác nhận.")
            disposition = "attachment; filename=\"document\"; filename*=UTF-8''" + quote(file["name"], safe="")
            url = self.storage.presign_get(file["object_key"], version_id, disposition, self.settings.download_ttl)
            self.audit(c, owner, "download_authorized", file_id, version_id)
            return {"url": url, "expires_in": self.settings.download_ttl, "version_id": version_id}

    def delete(self, owner, file_id):
        with self.lock, self.db() as c:
            file = self.owned(c, owner, file_id)
            if not file["active_version"]:
                raise Problem(409, "Tài liệu chưa hoàn tất tải lên.")
            if not file["deleted"]:
                marker = self.storage.delete(file["object_key"])
                c.execute("UPDATE files SET deleted=1,marker=? WHERE id=?", (marker, file_id))
                self.audit(c, owner, "soft_deleted", file_id, marker)
            return {"deleted": True}

    def restore(self, owner, file_id, version_id=None):
        with self.lock, self.db() as c:
            file = self.owned(c, owner, file_id)
            if version_id:
                version = c.execute("SELECT * FROM versions WHERE file_id=? AND version_id=?", (file_id, version_id)).fetchone()
                if not version:
                    raise Problem(404, "Không tìm thấy phiên bản đã xác nhận.")
                used = c.execute("SELECT COALESCE(SUM(v.size),0) FROM versions v JOIN files f ON f.id=v.file_id WHERE f.owner=?", (owner,)).fetchone()[0]
                reserved = c.execute("SELECT COALESCE(SUM(size),0) FROM uploads WHERE owner=? AND state='pending' AND expires>=?", (owner, self.clock())).fetchone()[0]
                if used + reserved + version["size"] > self.settings.quota_bytes:
                    raise Problem(409, "Khôi phục sẽ vượt hạn mức lịch sử 250 MiB.")
                new_version = self.storage.copy_version(file["object_key"], version_id)
                c.execute("INSERT INTO versions VALUES(?,?,?,?,?)", (file_id, new_version, version["size"], version["mime"], self.clock()))
                c.execute("UPDATE files SET active_version=?,deleted=0,marker=NULL WHERE id=?", (new_version, file_id))
                self.audit(c, owner, "version_restored", file_id, version_id)
            elif file["deleted"] and file["marker"]:
                self.storage.remove_marker(file["object_key"], file["marker"])
                c.execute("UPDATE files SET deleted=0,marker=NULL WHERE id=?", (file_id,))
                self.audit(c, owner, "delete_marker_removed", file_id)
            else:
                raise Problem(409, "Tài liệu chưa bị xóa. Chọn phiên bản nếu muốn phục hồi nội dung cũ.")
            return {"restored": True}

    def history(self, owner):
        with self.db() as c:
            return [dict(x) for x in c.execute("SELECT a.action,a.detail,a.at,f.name FROM audit a LEFT JOIN files f ON f.id=a.file_id WHERE a.owner=? ORDER BY a.id DESC LIMIT 100", (owner,)).fetchall()]


