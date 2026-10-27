from pathlib import Path
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from botocore.exceptions import BotoCoreError, ClientError
from .config import Settings
from .service import Problem, Vault
from .storage import S3Storage


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Strict):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


class Upload(Strict):
    name: str = Field(max_length=160)
    size: int = Field(strict=True, ge=1)
    file_id: str | None = Field(default=None, max_length=50)


class Complete(Strict):
    version_id: str = Field(min_length=1, max_length=256)


class Version(Strict):
    version_id: str | None = Field(default=None, max_length=256)


def create_app(vault=None):
    if vault is None:
        settings = Settings.from_env()
        vault = Vault(settings, S3Storage(settings))
    app = FastAPI(title="N11 Vault", version="1.0.0", docs_url=None, redoc_url=None)
    app.state.vault = vault
    bearer = HTTPBearer(auto_error=False)

    def credentials(auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if auth is None or auth.scheme.lower() != "bearer":
            raise Problem(401, "Vui lòng đăng nhập.")
        return auth.credentials

    def owner(token=Depends(credentials)):
        return vault.authenticate(token)

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(ClientError)
    async def storage_error(request, exc):
        code = exc.response.get("Error", {}).get("Code")
        status = 422 if code in ["NoSuchKey", "NoSuchVersion", "404"] else 503
        return JSONResponse({"detail": "Chưa tìm thấy dữ liệu đã tải. Hãy thử lại." if status == 422 else "Kho lưu trữ chưa sẵn sàng. Kiểm tra dịch vụ MinIO."}, status_code=status)

    @app.exception_handler(BotoCoreError)
    async def connection_error(request, exc):
        return JSONResponse({"detail": "Không kết nối được kho lưu trữ. Kiểm tra MinIO."}, status_code=503)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' " + vault.settings.public_endpoint + "; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.get("/api/health")
    def health():
        vault.storage.ready()
        return {"status": "ok", "storage": "MinIO", "deployment": "single-node local lab"}

    @app.post("/api/login")
    def login(body: Login, request: Request):
        return vault.login(body.username, body.password, request.client.host if request.client else "unknown")

    @app.post("/api/logout")
    def logout(token=Depends(credentials)):
        vault.logout(token)
        return {"ok": True}

    @app.get("/api/me")
    def me(user=Depends(owner)):
        return {"id": user, "name": vault.USERS[user]}

    @app.get("/api/files")
    def files(user=Depends(owner)):
        return vault.list_files(user)

    @app.post("/api/uploads")
    def upload(body: Upload, user=Depends(owner)):
        return vault.allocate(user, body.name, body.size, body.file_id)

    @app.post("/api/uploads/{upload_id}/complete")
    def complete(upload_id: str, body: Complete, user=Depends(owner)):
        return vault.complete(user, upload_id, body.version_id)

    @app.get("/api/files/{file_id}/versions")
    def versions(file_id: str, user=Depends(owner)):
        return vault.versions(user, file_id)

    @app.post("/api/files/{file_id}/download")
    def download(file_id: str, body: Version, user=Depends(owner)):
        return vault.download(user, file_id, body.version_id)

    @app.delete("/api/files/{file_id}")
    def delete(file_id: str, user=Depends(owner)):
        return vault.delete(user, file_id)

    @app.post("/api/files/{file_id}/restore")
    def restore(file_id: str, body: Version, user=Depends(owner)):
        return vault.restore(user, file_id, body.version_id)

    @app.get("/api/audit")
    def audit(user=Depends(owner)):
        return {"events": vault.history(user)}

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app
