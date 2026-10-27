# Amazon S3 và cổng tài liệu riêng tư với MinIO

Học viện Công nghệ Bưu chính Viễn thông · Khoa Viễn thông 1 · Nhóm 11

**Giảng viên hướng dẫn: TS Phạm Hùng**

Thành viên: Nguyễn Minh Hiếu, Nguyễn Đăng Minh, Phương Bảo Vỹ, Phan Nguyễn Trung Khánh.

## Tài liệu và sản phẩm

- [Báo cáo Word](docs/Bao_cao_Nhom_11_S3_MinIO.docx)
- [Slide Canva chỉnh sửa được](https://www.canva.com/d/FhStqU6JITMdV8l)
- [Slide PowerPoint](docs/Slide_Nhom_11_S3_MinIO.pptx)
- [Bản rà soát kiến thức](docs/Ra_soat_kien_thuc.md)
- [Nguồn chính thức](docs/sources.json)
- [Bằng chứng kiểm thử tích hợp thật](test-evidence.json)

Đã đạt 27 kiểm thử unit/security/API và 15 tình huống tích hợp với MinIO thật. Bản chạy một nút phục vụ học tập; chưa đo hiệu năng hoặc chứng minh HA. Nội dung slide giữ bốn phần và thứ tự 28 chủ đề trong đề cương, có hiệu đính theo nguồn chính thức ngày 27/10/2026.

# N11 Vault — Cổng tài liệu riêng và khôi phục phiên bản

Bản thực nghiệm của Nhóm 11, Khoa Viễn thông 1, Học viện Công nghệ Bưu chính Viễn thông. Bài toán: tài liệu bị ghi đè, xóa nhầm, chia sẻ link công khai và backend phải trung chuyển toàn bộ tệp. Sản phẩm cho phép mỗi người nộp tài liệu riêng, tải trực tiếp tới kho S3, xem lịch sử và phục hồi nội dung.

## Chạy trên Windows: chỉ cần Docker Desktop

1. Mở Docker Desktop, đợi **Engine running**. Chọn Linux containers. Máy cần Internet để tải image và build MinIO từ source lần đầu; nên dành khoảng 4 GiB RAM khả dụng cho Docker.
2. Mở PowerShell trong thư mục này và chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Script tự tìm Docker trong PATH hoặc đường dẫn cài Docker Desktop của người dùng; tạo `.env` ngẫu nhiên **chỉ khi chưa tồn tại**; build và khởi động dịch vụ. Lần đầu có thể mất vài phút do biên dịch MinIO.

3. Mở **http://localhost:8000**. Script in mật khẩu ứng dụng cho `hieu` và `minh`. Có thể đọc lại hai dòng `DEMO_PASSWORD_HIEU`/`DEMO_PASSWORD_MINH` trong `.env`. Không dùng tài khoản MinIO root trên giao diện ứng dụng.
4. Những lần sau có thể dùng `powershell -ExecutionPolicy Bypass -File .\start.ps1 -NoBuild` nếu không sửa mã nguồn.

MinIO API: `http://localhost:9000`. Cả hai cổng chỉ bind `127.0.0.1`. Console quản trị không được xuất ra ngoài; mọi thao tác demo thực hiện trên ứng dụng. CORS chỉ chấp nhận origin `http://localhost:8000`; hãy dùng đúng địa chỉ này thay cho `127.0.0.1:8000` hoặc máy khác.

Trên macOS/Linux hoặc máy đã có Python 3.12:

```sh
python setup_env.py
docker compose up --build -d
```

Nếu không có Python, tự sao chép `.env.example` thành `.env` và thay **tất cả** giá trị bằng bí mật ngẫu nhiên khác nhau dài từ 12 ký tự. Docker-only launcher Windows là cách khuyến nghị trên máy hiện tại.

## Kịch bản thuyết trình 7–10 phút

| Bước | Thao tác | Kết quả cần quan sát |
|---|---|---|
| 1 | Đăng nhập `hieu`, tải một `.txt` hoặc PDF nhỏ | Ứng dụng cấp quyền, trình duyệt PUT trực tiếp tới cổng 9000, API chỉ xác nhận metadata |
| 2 | Mở DevTools → Network khi tải/tải xuống | PUT/GET mang byte tệp đi tới MinIO; request `/api/` là JSON điều khiển |
| 3 | Chép URL object, bỏ query chữ ký rồi mở lại | MinIO trả HTTP 403; bucket không public |
| 4 | Bấm **Bản mới** trên cùng tài liệu, chọn nội dung đã sửa cùng định dạng | Hai version ID khác nhau; tải riêng từng bản trong **Lịch sử** |
| 5 | Xóa tài liệu, mở **Thùng rác**, bấm **Khôi phục** | Delete marker thực được tạo rồi gỡ; nội dung đã xác nhận còn nguyên |
| 6 | Trong **Lịch sử**, khôi phục nội dung một bản cũ | CopyObject phía kho tạo một version mới; các version cũ vẫn giữ lại |
| 7 | Đăng xuất, đăng nhập `minh` | Không nhìn thấy tài liệu `hieu`; gọi API bằng ID của `hieu` nhận 404 |
| 8 | Lấy presigned GET, dùng hai lần trước hạn; chờ quá 60 giây rồi dùng lại | URL là bearer token dùng lại được trước hạn; sau hạn MinIO từ chối |

Không trình chiếu `.env`, token đăng nhập hoặc toàn bộ presigned URL lên màn hình công khai. Presigned URL chứa access-key ID và chữ ký, không chứa secret key; người có URL có thể sử dụng quyền đó đến khi hết hiệu lực.

## Luồng dữ liệu và cơ chế kiểm soát

```text
Trình duyệt ── JSON + bearer session ──> FastAPI ── metadata/audit ──> SQLite
    │                                     │
    │                                     └── boto3 ký URL / HEAD / COPY / DELETE
    └────────── presigned PUT / GET ───────────────────────────────> MinIO
```

- Hai tài khoản demo có mật khẩu riêng. Backend ánh xạ token ngẫu nhiên 256 bit sang danh tính; phiên hết hạn sau một giờ, mất khi restart và bị thu hồi khi đăng xuất. Có giới hạn thử đăng nhập 8 lần sai/phút/IP. Đây là xác thực lab, chưa phải SSO/OIDC.
- Mọi thao tác tài liệu kiểm tra chủ sở hữu ở backend. Client không được chọn owner, bucket hoặc object key. Khóa kho do server sinh: `users/{owner}/{uuid}`; tên hiển thị không được dùng như đường dẫn.
- Cấp phát upload có TTL 180 giây và metadata `upload-id` đã ký. Sau PUT, trình duyệt lấy `x-amz-version-id` rồi gọi finalize. Backend HEAD **đúng version** để kiểm tra kích thước, MIME header và mã upload trước khi ghi catalog.
- Mỗi tài liệu chỉ tải các version ID đã được finalize. URL PUT có thể dùng lại trong TTL và sinh thêm phiên bản vật lý; bản phát lại chưa được xác nhận không thể tự thay thế nội dung đã công bố trong ứng dụng.
- Download luôn ký GET cho version ID đã xác nhận, TTL 60 giây, ép tải dạng attachment/octet-stream. URL không phải liên kết dùng một lần. TTL áp dụng khi kho kiểm tra request; không hứa ngắt một lượt tải đã bắt đầu trước hạn.
- Xóa là DeleteObject tạo delete marker. Khôi phục xóa mềm gỡ đúng marker đã ghi nhận. Khôi phục nội dung cũ COPY phía MinIO thành một phiên bản mới. UI hiển thị lịch sử **đã xác nhận trong catalog**, không tuyên bố liệt kê mọi version vật lý do upload lỗi/phát lại.
- MinIO root chỉ được truyền cho dịch vụ bootstrap một lần. App chạy bằng user MinIO riêng, policy giới hạn một bucket và prefix `users/*`, không có quyền quản trị. Hai tài khoản ứng dụng dùng chung service user; ranh giới người dùng do backend thực thi. Đây chưa phải IAM user/STS riêng cho từng người.
- Bucket mới không có policy public; bootstrap xóa policy anonymous nếu có và bật versioning. Cấu hình CORS dùng `MINIO_API_CORS_ALLOW_ORIGIN` của MinIO; không gọi PutBucketCors vì release này không hỗ trợ API ghi đó.

## API

| Phương thức | Đường dẫn | Mục đích |
|---|---|---|
| POST | `/api/login`, `/api/logout` | Tạo/thu hồi phiên ứng dụng |
| GET | `/api/me`, `/api/health` | Danh tính và kiểm tra kho thật |
| GET | `/api/files` | Catalog riêng và dung lượng lịch sử đã xác nhận |
| POST | `/api/uploads` | Cấp URL PUT cho tài liệu mới hoặc `file_id` có sẵn |
| POST | `/api/uploads/{upload_id}/complete` | Xác nhận `version_id` sau PUT |
| GET | `/api/files/{file_id}/versions` | Lịch sử đã xác nhận và marker đã ghi |
| POST | `/api/files/{file_id}/download` | Cấp GET cho bản đang chọn hoặc `version_id` |
| DELETE | `/api/files/{file_id}` | Xóa mềm bằng delete marker |
| POST | `/api/files/{file_id}/restore` | Gỡ marker; hoặc copy một `version_id` cũ thành bản mới |
| GET | `/api/audit` | Tối đa 100 sự kiện ứng dụng của tài khoản |

## Kiểm thử có thể chạy lại

Unit/security tests dùng memory S3 double cho nghiệp vụ; một test sinh chữ ký thật bằng boto3, không gọi kho. Cài vào venv riêng:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate ; Linux/macOS: source .venv/bin/activate
pip install -r requirements-test.txt
python -m pytest tests -q
```

Kiểm thử tích hợp dùng stack **MinIO thật** đang chạy, chỉ cần Python tiêu chuẩn:

```sh
python integration_check.py
```

Không có host Python thì chạy bằng container Python và mạng host của Docker Desktop (cần bật tính năng host networking); hoặc dùng Python cài sẵn của máy. `integration_check.py` có BaseURL localhost vì presigned URL đã ký hostname; không thay hostname trong URL sau khi ký. Kịch bản chờ expiry thật khoảng 64 giây, tạo một số tài liệu minh họa và một tệp ở thùng rác. Mỗi lần chạy tạo dữ liệu mới. Kết quả nằm ở `test-evidence.json`, không lưu token/URL ký.

Bộ test **không đo** thông lượng, CPU/RAM, độ bền dữ liệu, HA hoặc fault tolerance. Giảm đường đi byte qua backend là tính chất luồng đã kiểm tra; không suy diễn thành số phần trăm tăng tốc.

## Phạm vi và việc còn thiếu

- **Một MinIO node, một Docker volume trên một máy**. Đây là lab S3 API/versioning, không phải cụm phân tán và không chịu được mất máy/ổ đĩa. Docker named volume giúp dữ liệu tồn tại khi tạo lại container, không thay thế backup.
- Cơ sở MinIO community đã lưu trữ/không còn được duy trì ở thời điểm rà soát 27/10/2026. Dockerfile biên dịch source official release `RELEASE.2025-10-15T17-29-55Z` (commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`) để tái lập lab, **không phải khuyến nghị production**. Không dựa vào image `latest`/console cũ. MinIO mang giấy phép AGPLv3; Docker image giữ bản LICENSE. Source: https://github.com/minio/minio/tree/RELEASE.2025-10-15T17-29-55Z . App riêng và source nguồn MinIO có phạm vi giấy phép tương ứng; cần tự rà soát khi phân phối/sử dụng ngoài lab.
- Chấp nhận tệp 1 byte–25 MiB và hạn mức lịch sử đã xác nhận 250 MiB/tài khoản, tính cả phiên bản cũ và tài liệu thùng rác. Đây là **hạn mức catalog**, không phải quota vật lý cứng: PUT có thể gửi quá dung lượng khai báo rồi bị finalize từ chối; replay/upload bỏ dở tạo phiên bản vật lý chưa được quản lý. Cần POST policy có `content-length-range`, quota phía kho, hạn mức request và cleanup trước khi mở hệ thống thật.
- Giới hạn MIME theo đuôi tên và Content-Type header; **không quét mã độc hoặc xác minh bytes là PDF/ZIP hợp lệ**. Không render nội dung trong trang. Chỉ dùng dữ liệu giả lập, không tải tài liệu nhạy cảm thật vào lab HTTP này.
- Chưa có multipart/resume, event worker, thumbnail, antivirus/quarantine, TLS, KMS, Object Lock, OIDC, nhóm chia sẻ thật, backup offsite hoặc dashboard benchmark. Nhật ký SQLite ghi thao tác ứng dụng/cấp quyền; không chứng minh GET đã tải xong và không chống sửa bởi quản trị viên.
- SQLite một tiến trình và phiên lưu RAM: chỉ chạy một Uvicorn worker. Giao dịch DB và thao tác S3 không có transaction chung; lỗi giữa hai bước có thể để lại orphan; phục hồi cần đối soát. Không sửa object/marker trực tiếp bằng admin trong lúc dùng app.

## Dữ liệu, dừng dịch vụ và xử lý lỗi

```sh
docker compose ps
docker compose logs --tail=80 app bootstrap minio
docker compose stop
# Chạy lại và giữ dữ liệu:
docker compose start minio app
```

`docker compose down` gỡ container/network và giữ named volumes. **Không chạy `down -v` nếu cần giữ dữ liệu**, vì lệnh đó xóa vĩnh viễn cả SQLite catalog và kho tệp. Giữ `.env` tương ứng với volumes; đổi/xóa bí mật tùy tiện có thể làm ứng dụng không truy cập được dữ liệu cũ.

Nếu bootstrap lỗi `policy` khi chạy lại, kiểm tra log; script hỗ trợ thông báo policy đã áp dụng. Nếu upload báo không có version ID, kiểm tra versioning, CORS expose `x-amz-version-id`, dùng đúng origin localhost:8000 và làm mới trang. Nếu chữ ký không hợp lệ, kiểm tra đồng hồ hệ thống và giữ nguyên hostname/cổng của URL đã ký. Nếu không có `docker` trong PATH, dùng `start.ps1` hoặc đường dẫn `docker.exe` mà script tìm được.

Cleanup orphan: bản lab không tự xóa phiên bản cũ, để tránh mất lịch sử đã xác nhận. Trước khi mở thật cần job đối soát `ListObjectVersions` với bảng `versions` và delete marker đã ghi trong SQLite; bỏ qua upload còn hiệu lực; chỉ xóa orphan sau một khoảng an toàn (ví dụ 24 giờ) và bản sao lưu. Không bật lifecycle `NoncurrentVersionExpiration` bừa bãi vì nó có thể xóa các version mà catalog còn tham chiếu. Cleanup multipart incomplete có thể bổ sung khi có multipart; hiện demo chỉ dùng single PUT.

## Tài liệu chính thức

- Amazon S3 presigned URL: https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html
- S3 versioning/delete marker: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html
- Boto3 presigned URLs: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
- MinIO source/release: https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z
- MinIO Admin Python: https://github.com/minio/minio-py/blob/7.2.15/minio/minioadmin.py
