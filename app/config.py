import os
from dataclasses import dataclass


@dataclass
class Settings:
    database: str = "data/vault.db"
    bucket: str = "nhom11-private"
    internal_endpoint: str = "http://minio:9000"
    public_endpoint: str = "http://localhost:9000"
    access_key: str = ""
    secret_key: str = ""
    password_hieu: str = ""
    password_minh: str = ""
    upload_ttl: int = 180
    download_ttl: int = 60
    max_file_bytes: int = 25 * 1024 * 1024
    quota_bytes: int = 250 * 1024 * 1024

    @classmethod
    def from_env(cls):
        value = cls(
            database=os.getenv("DATABASE_PATH", "data/vault.db"),
            bucket=os.getenv("S3_BUCKET", "nhom11-private"),
            internal_endpoint=os.getenv("S3_INTERNAL_ENDPOINT", "http://minio:9000"),
            public_endpoint=os.getenv("S3_PUBLIC_ENDPOINT", "http://localhost:9000"),
            access_key=os.getenv("S3_ACCESS_KEY", ""),
            secret_key=os.getenv("S3_SECRET_KEY", ""),
            password_hieu=os.getenv("DEMO_PASSWORD_HIEU", ""),
            password_minh=os.getenv("DEMO_PASSWORD_MINH", ""),
        )
        for secret in [value.access_key, value.secret_key, value.password_hieu, value.password_minh]:
            if len(secret) < 12:
                raise RuntimeError("Thiếu cấu hình bí mật. Chạy python setup_env.py trước.")
        if value.password_hieu == value.password_minh:
            raise RuntimeError("Hai tài khoản demo cần mật khẩu khác nhau.")
        return value
