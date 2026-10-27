"""One-time infrastructure step. Root secrets are only injected into this container."""
import json
import os
import tempfile
from urllib.parse import urlsplit
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from minio.minioadmin import MinioAdmin
from minio.credentials import StaticProvider
from minio.error import MinioAdminException

endpoint = os.environ["S3_INTERNAL_ENDPOINT"]
root, secret = os.environ["MINIO_ROOT_USER"], os.environ["MINIO_ROOT_PASSWORD"]
bucket = os.environ["S3_BUCKET"]
s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=root, aws_secret_access_key=secret,
                  region_name="us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
try:
    s3.head_bucket(Bucket=bucket)
except ClientError as exc:
    if exc.response["Error"]["Code"] not in ["404", "NoSuchBucket"]:
        raise
    s3.create_bucket(Bucket=bucket)
# Fail closed: remove any anonymous bucket policy, then enable versioning.
s3.delete_bucket_policy(Bucket=bucket)
s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
policy = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketLocation"],
     "Resource": [f"arn:aws:s3:::{bucket}"]},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion"],
     "Resource": [f"arn:aws:s3:::{bucket}/users/*"]}]}
url = urlsplit(endpoint)
admin = MinioAdmin(url.netloc, StaticProvider(root, secret), secure=url.scheme == "https")
admin.user_add(os.environ["S3_ACCESS_KEY"], os.environ["S3_SECRET_KEY"])
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as file:
    json.dump(policy, file)
    policy_path = file.name
try:
    admin.policy_add("nhom11-app-private", policy_path)
    try:
        admin.attach_policy(["nhom11-app-private"], user=os.environ["S3_ACCESS_KEY"])
    except MinioAdminException as exc:
        message = str(exc).lower()
        if "already" not in message and "no net effect" not in message:
            raise
finally:
    os.unlink(policy_path)
assert s3.get_bucket_versioning(Bucket=bucket).get("Status") == "Enabled"
print("Bootstrap hoàn tất: bucket private, versioning bật, app user giới hạn một bucket.")

