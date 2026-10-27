import boto3
from botocore.config import Config


class S3Storage:
    def __init__(self, settings):
        self.bucket = settings.bucket
        common = dict(aws_access_key_id=settings.access_key,
                      aws_secret_access_key=settings.secret_key, region_name="us-east-1",
                      config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                                    connect_timeout=3, read_timeout=15,
                                    retries={"max_attempts": 2}))
        self.client = boto3.client("s3", endpoint_url=settings.internal_endpoint, **common)
        self.signer = boto3.client("s3", endpoint_url=settings.public_endpoint, **common)

    def ready(self):
        self.client.head_bucket(Bucket=self.bucket)

    def presign_put(self, key, mime, upload_id, ttl):
        headers = {"Content-Type": mime, "x-amz-meta-upload-id": upload_id}
        url = self.signer.generate_presigned_url("put_object", Params={
            "Bucket": self.bucket, "Key": key, "ContentType": mime,
            "Metadata": {"upload-id": upload_id}}, ExpiresIn=ttl)
        return url, headers

    def head(self, key, version):
        r = self.client.head_object(Bucket=self.bucket, Key=key, VersionId=version)
        return {"size": r["ContentLength"], "mime": r["ContentType"],
                "upload_id": r.get("Metadata", {}).get("upload-id"), "version_id": r["VersionId"]}

    def presign_get(self, key, version, disposition, ttl):
        return self.signer.generate_presigned_url("get_object", Params={
            "Bucket": self.bucket, "Key": key, "VersionId": version,
            "ResponseContentDisposition": disposition,
            "ResponseContentType": "application/octet-stream"}, ExpiresIn=ttl)

    def delete(self, key):
        r = self.client.delete_object(Bucket=self.bucket, Key=key)
        if not r.get("DeleteMarker") or not r.get("VersionId"):
            raise RuntimeError("Bucket phải bật versioning trước khi chạy.")
        return r["VersionId"]

    def remove_marker(self, key, marker):
        self.client.delete_object(Bucket=self.bucket, Key=key, VersionId=marker)

    def copy_version(self, key, version):
        r = self.client.copy_object(Bucket=self.bucket, Key=key,
            CopySource={"Bucket": self.bucket, "Key": key, "VersionId": version},
            MetadataDirective="COPY")
        return r["VersionId"]
