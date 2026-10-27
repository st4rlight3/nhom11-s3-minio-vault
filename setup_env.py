"""Create local lab secrets once; never replace an existing .env automatically."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent / ".env"
if path.exists():
    raise SystemExit(".env đã tồn tại. Giữ nguyên để tiếp tục truy cập dữ liệu cũ.")
values = {name: secrets.token_urlsafe(24) for name in [
    "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "S3_ACCESS_KEY", "S3_SECRET_KEY",
    "DEMO_PASSWORD_HIEU", "DEMO_PASSWORD_MINH"]}
with path.open("x", encoding="utf-8") as file:
    file.write("# Local-only lab secrets. Keep this file private.\n")
    file.writelines(f"{name}={value}\n" for name, value in values.items())
print("Đã tạo .env. Mật khẩu ứng dụng (không phải MinIO root):")
print("hieu:", values["DEMO_PASSWORD_HIEU"])
print("minh:", values["DEMO_PASSWORD_MINH"])
print("Chạy docker compose up --build -d, rồi mở http://localhost:8000")

