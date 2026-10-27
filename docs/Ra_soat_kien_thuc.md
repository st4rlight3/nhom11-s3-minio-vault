# Rà soát đề cương Amazon S3 / MinIO — Nhóm 11

Ngày đối chiếu nguồn chính thức: **27/10/2026**. Tài liệu gốc: bản đề cương 28 slide do người dùng cung cấp. Đây là kết quả kiểm tra kiến thức và đề xuất thiết kế, **không phải biên bản chạy thực nghiệm**.

## 1. Kết luận để quyết định sản phẩm

Đề cương có trục nội dung hợp lý: object storage → quản trị S3 → presigned URL → MinIO. Tuy nhiên, chưa nên dựng nguyên trạng thành slide: có thông số lỗi thời, kết luận tuyệt đối và mô tả demo chưa có bằng chứng. Cần chuyển phần thực hành thành **cổng nộp bài và quản lý tài liệu nhóm riêng tư**, để mỗi tính năng trả lời một nhu cầu rõ ràng.

Tiêu đề nên dùng: **“Amazon S3 và ứng dụng lưu trữ tương thích S3: xây dựng cổng tài liệu nhóm riêng tư với MinIO”**. Nếu bản chạy chỉ có một tiến trình/một ổ đĩa, không gọi kết quả đó là “cụm phân tán”, “chịu lỗi ổ đĩa” hoặc “đạt độ bền như AWS”. Có thể trình bày kiến trúc phân tán trong phần nghiên cứu và ghi là hướng mở rộng cần kiểm chứng.

## 2. Những lỗi và phát biểu cần sửa ngay

| Mức | Nội dung gốc | Nội dung thay thế / lý do | Nguồn |
|---|---|---|---|
| Bắt buộc | Object tối đa 5 TB, lặp ở slide 3 và 12 | AWS công bố tăng tối đa lên **50 TB từ 02/12/2025**. User Guide ghi giới hạn multipart **48,8 TiB**, 10.000 phần, mỗi phần 5 MiB–5 GiB trừ phần cuối. Giữ nguyên cách ghi đơn vị của nguồn, không tự đồng nhất TB thập phân với TiB. Ngưỡng PUT đơn vẫn 5 GB; nên cân nhắc multipart từ 100 MB. | [S01], [S02], [S03] |
| Bắt buộc | “MinIO hiện thực 100% chuẩn S3”, “tương thích tuyệt đối” | Dùng “tương thích nhiều thao tác S3 phổ biến; cần kiểm thử tập API sử dụng”. Tài liệu AIStor có danh sách API không hỗ trợ, ví dụ Object ACL, PublicAccessBlock, Website. Không suy rộng tính năng AIStor mới sang Community cũ. | [S04], [S05] |
| Bắt buộc | MinIO Community như một lựa chọn production đang phát triển bình thường | Repo `minio/minio` hiện archived, chỉ đọc từ **25/04/2026**, README ghi không còn được bảo trì; Community phân phối source-only và mang AGPLv3. README giới thiệu AIStor Free cho standalone và AIStor Enterprise cho distributed có hỗ trợ thương mại. Vì vậy lab cần ghim phiên bản/commit, kiểm chứng cách build/run và ghi rõ giới hạn. Không hứa có image `latest`, bản nhị phân mới hoặc Console quản trị đầy đủ. | [S04] |
| Bắt buộc | “99,99% Availability” như một bảo đảm chung | **S3 Standard được thiết kế cho 99,99% availability**, độ bền 11 số 9 theo năm. SLA và điều kiện service credit khác: Standard bắt đầu credit khi uptime tháng dưới 99,9%. Không áp cùng một mức cho mọi storage class. | [S06], [S07], [S08] |
| Bắt buộc | Mọi object S3 được nhân bản ≥3 AZ | Nhiều lớp đa AZ lưu trên tối thiểu 3 AZ trong một Region; One Zone-IA và Express One Zone nằm trong **1 AZ**. Không nói AWS có đúng “3 bản sao”: số AZ không phải số replica đã công bố. | [S06], [S07] |
| Bắt buộc | Strong consistency chỉ cho PUT/DELETE “mới” | Bao gồm PUT mới, ghi đè và DELETE; GET/LIST sau ghi thành công phản ánh kết quả mới, HEAD/metadata cũng nhất quán mạnh. Tính nguyên tử theo **một key**; không tạo transaction đa key, không biến CRR thành đồng bộ. Một số cấu hình bucket có eventual consistency. | [S09] |
| Bắt buộc | Glacier “vài phút đến 12 giờ” dùng chung Deep Archive | Flexible Retrieval: phút–12 giờ với các tier thông thường; Deep Archive: Standard khoảng 12 giờ, Bulk khoảng 48 giờ. Tài liệu hiện có thêm trường hợp batch/đối tượng >5 TB nên đây không là cam kết chung cho mọi object. Minimum storage duration: Flexible 90 ngày, Deep Archive 180 ngày. | [S10] |
| Bắt buộc | S3 Select là phương án nên triển khai mới | S3 Select **không còn nhận khách hàng mới**. Nêu như tính năng lịch sử, hoặc chuyển slide chính sang Athena + partitioning/Parquet. Bỏ con số tiết kiệm băng thông 80–90% khi không có workload/đo lường. | [S11] |
| Bắt buộc | Athena = Presto engine | Với SQL engine v3, AWS mô tả nền tảng **Trino**; engine v2 dựa Presto. Nói “Athena SQL truy vấn dữ liệu trên S3, engine v3 dựa Trino”. | [S12] |
| Bắt buộc | 3.500 ghi, 5.500 đọc mỗi prefix là “lên tới” | AWS công bố mức **ít nhất** 3.500 PUT/COPY/POST/DELETE và 5.500 GET/HEAD request/giây/prefix. Đây không phải trần và không phải số đo của lab MinIO. Scale cần thời gian; client cần retry/backoff khi có 503 Slow Down. | [S13] |
| Bắt buộc | URL có TTL “tự hủy”, bảo đảm chỉ người được nhận sử dụng | URL là **bearer token**: người giữ link có thể sử dụng; URL có thể tái dùng trước hết hạn. Expiry không xóa file. Credential hết hạn/bị thu hồi hoặc quyền không còn cho phép có thể khiến URL mất hiệu lực sớm. S3 kiểm expiry khi request bắt đầu; download đã bắt đầu có thể tiếp tục. | [S14], [S15] |
| Bắt buộc | Lifecycle ngày365 “tiêu hủy vĩnh viễn tệp” | Với versioning bật, Expiration của current version thường thêm delete marker; NoncurrentVersionExpiration mới xóa version cũ. Cần quy tắc cho version cũ, delete marker và multipart chưa hoàn tất tùy chính sách. Không gắn mốc mẫu như 30/90/365 cho mọi tổ chức. | [S16] |
| Bắt buộc | Xóa luôn chỉ thêm delete marker | Đúng với **simple DELETE trên bucket versioning enabled**. Xóa một version bằng versionId có thể là xóa vĩnh viễn nếu có quyền và không bị khóa. Khôi phục bằng bỏ marker chỉ khả thi nếu version cần dùng còn tồn tại. | [S16], [S17] |
| Nên sửa | “4 thành phần object: key, value, metadata(tags), versionID” | Trình bày: object gồm dữ liệu và metadata, nằm trong bucket và được định danh bằng key; tags là tập key-value được quản lý riêng, user-defined metadata là các cặp header `x-amz-meta-*`; versionId có giá trị riêng khi bật versioning (object không version có `null`). | [S18], [S19], [S20] |
| Nên sửa | Object Lock khóa cứng mọi chỉnh sửa của file | Lock bảo vệ **object version**, với Governance/Compliance hoặc legal hold. Governance có quyền bypass; khóa version không cấm tạo version mới hay thêm delete marker. Không đồng nhất WORM với chống mọi rủi ro ransomware. | [S17] |
| Nên sửa | Event pipeline tự động “hoàn toàn” | AWS có SNS, SQS, Lambda và EventBridge. Notification có thể trễ, lặp, không đúng thứ tự; worker cần idempotency, retry và quan sát trạng thái. Tránh trigger lặp khi worker ghi ngược cùng prefix. | [S21], [S22] |
| Nên sửa | Replication = backup / DR hoàn chỉnh | CRR/SRR là sao chép bất đồng bộ. Live replication chủ yếu áp dụng dữ liệu mới/sửa sau cấu hình; object cũ cần Batch Replication. Cần thêm RPO/RTO, phân tách quyền, bảo vệ xóa và thử khôi phục mới đánh giá DR. | [S23] |
| Nên sửa | SSE-S3, SSE-KMS, SSE-C được nêu như tương đương | S3 mã hóa mặc định object tải mới bằng SSE-S3 từ 05/01/2023; lựa chọn KMS phục vụ quản trị khóa/audit theo nhu cầu. TLS phải được thực thi bằng endpoint/policy. Lab HTTP localhost không được mô tả là đã có TLS/SSE-KMS. | [S24] |
| Nên sửa | “Không qua proxy trung gian”, FastAPI “không tiêu tốn băng thông” | Object bytes đi trực tiếp client↔storage, tránh đi qua **application backend**. Backend vẫn có traffic metadata/xác thực/ký URL; storage vẫn có thể qua ingress/load balancer/reverse proxy. Chỉ nói giảm lưu lượng payload qua backend, không mặc định CPU/RAM bằng0 hay nhanh hơn. | Phân tích kiến trúc; cần đo |

## 3. Kiến thức đang thừa, thiếu và cách cân bằng 28 slide

**Giảm:** lịch sử DAS→NAS→Object quá tuyến tính; các loại cùng tồn tại, SAN/NAS hiện đại vẫn scale-out. Không mô tả object storage là dung lượng vô hạn về vật lý hoặc luôn rẻ nhất. Chọn theo IO pattern, latency, semantics, quy mô và tổng chi phí. Các slide Event, Select/Athena, Replication nên gom thành bức tranh mở rộng hoặc phụ lục; tránh để demo mất trọng tâm.

**Bổ sung bắt buộc:** mục tiêu/người sử dụng; 3 nỗi đau có tiêu chí kiểm chứng; phân biệt tính năng nghiên cứu với tính năng đã chạy; mô hình quyền theo nhóm; key do server cấp thay vì tin filename; trạng thái upload pending/verified; kiểm tra dung lượng/checksum; endpoint client truy cập được; CORS; giới hạn của bearer URL; khôi phục sau xóa nhầm; bảng kết quả không điền số trước khi chạy; vận hành/backup/TLS/rate limit khi ra production.

**Phân bổ đề nghị:** 1 bìa; 2 bài toán thực tế; 3 mục tiêu và phạm vi; 4 object model; 5 Block/File/Object; 6 hệ sinh thái; 7 consistency/durability/availability; 8 storage classes; 9 lifecycle và chi phí; 10 policy/mã hóa; 11 presigned URL và rủi ro; 12 versioning/Object Lock; 13 multipart/integrity/performance; 14 analytics/events/replication như mở rộng; 15 MinIO hiện trạng 2026; 16 yêu cầu sản phẩm; 17 kiến trúc proxy/direct; 18 kiến trúc lab và trust boundaries; 19 cấp quyền upload; 20 quyền nhóm/private; 21 demo direct upload; 22 demo download và TTL; 23 demo ghi đè/versions; 24 demo xóa nhầm/restore; 25 kiểm thử và bằng chứng; 26 FinOps/giới hạn; 27 kết luận/hướng phát triển; 28 nguồn. Tên GVHD phải đứng trước tên thành viên ở bìa/lời giới thiệu theo yêu cầu người dùng.

## 4. Demo đề nghị: cổng tài liệu nhóm riêng tư

### Người dùng và nỗi đau

- Thành viên nhóm nộp báo cáo, slide, ảnh, video minh chứng; người hướng dẫn xem tài liệu nhóm được phân quyền.
- Lỗi thực tế: link công khai bị chuyển tiếp, bài bị ghi đè/xóa nhầm, backend ứng dụng phải relay tệp lớn, nhầm tài liệu giữa các nhóm.
- MinIO hợp lý cho lab và bối cảnh dữ liệu nội bộ; một cổng LMS thông thường có thể dùng S3 managed hoặc dịch vụ file có sẵn. Giá trị của demo là mẫu kiến trúc và kiểm chứng quyền/khôi phục, không phải tuyên bố đã thay thế LMS/Google Drive.

### Luồng tối thiểu có ý nghĩa

1. Đăng nhập tài khoản demo có group_id/role. Không cho client tự chọn identity bằng tham số không xác thực.
2. Backend kiểm tra quyền nộp bài, deadline, quota; cấp key theo namespace `groups/11/<document_id>/...` và upload record. Filename hiển thị được lưu riêng; key không được ghép tùy ý từ path client.
3. Cấp presigned PUT thời hạn ngắn, ràng buộc Content-Type/checksum được hỗ trợ và chính xác bucket/key/method; hoặc presigned POST có content-length-range khi mục tiêu chính là giới hạn upload ở storage. Không xem Content-Type khai báo là bằng chứng file an toàn.
4. Browser tải trực tiếp lên storage qua CORS đã cấu hình, sau đó gọi complete/finalize. Backend HEAD xác minh object/version, dung lượng, checksum/metadata phù hợp rồi mới đánh dấu hoàn tất. Giới hạn frontend chỉ là UX; không phải security control. HEAD kiểm sau upload không ngăn dữ liệu quá cỡ tiêu thụ băng thông/dung lượng ban đầu.
5. Backend kiểm quyền theo document_id khi list/download/version/restore; cấp GET URL cho đúng version nếu cần. Không chỉ kiểm tra prefix từ một chuỗi người dùng gửi.
6. Lưu audit event cho người thao tác, object/version, thời điểm và kết quả; không ghi nguyên URL có chữ ký hoặc secret vào log/UI minh chứng.

### Quy tắc production còn thiếu trong lab

TLS, secret manager và signer least privilege; SSO/OIDC; quota/rate limit được thực thi; antivirus/quarantine; policy retention; giám sát và alert; backup độc lập và restore drill; reconciliation pending uploads; persistent database và migration. Backend ký URL bằng account root chỉ chấp nhận cho bootstrap lab được cô lập, không cho sản phẩm thực tế. Một URL đã phát hành có thể còn dùng sau khi role ứng dụng bị thu hồi, trừ khi backend/storage còn có cơ chế thu hồi tương ứng; TTL ngắn chỉ thu hẹp thời gian này.

## 5. Ma trận kiểm chứng trước khi nói “đã giải quyết”

| ID | Thao tác | Kết quả cần thấy | Bằng chứng phải lưu |
|---|---|---|---|
| T01 | Anonymous GET object private | Bị từ chối, ghi đúng status/body thực tế | HTTP response + thời điểm |
| T02 | Thành viên11 upload trực tiếp | Storage nhận object, complete xác nhận | Network request đi cổng storage, version/size/checksum |
| T03 | Thành viên nhóm khác xin URL tài liệu11 | API từ chối trước khi ký | Response API, không phát URL |
| T04 | Thay key/method/signed header của URL | Chữ ký/quyền không hợp lệ | Response storage thực tế |
| T05 | GET URL trong TTL rồi gửi request mới sau TTL | Trước thành công, sau bị từ chối | Thời gian phát hành/gọi, status/body; không cache |
| T06 | Dùng lại URL trước TTL | Thường vẫn hợp lệ | Kết quả để minh họa bearer/reuse; không gọi single-use |
| T07 | Nộp v1/v2 cho cùng document | Hai version truy xuất độc lập | Hai versionId, tải nội dung/hash từng version |
| T08 | Simple delete rồi restore | GET current không thấy; version cũ còn; restore lại được | Delete marker ID, kết quả trước/sau |
| T09 | File quá cỡ / metadata sai | API từ chối hoặc finalize không công nhận | Record trạng thái lỗi, object cleanup; nêu rõ chặn trước hay phát hiện sau |
| T10 | Backend proxy vs direct, cùng workload | Payload qua app backend giảm ở direct | Bytes in/out, thời gian, lỗi, cấu hình và cỡ mẫu thực tế |

CPU/RAM chỉ là chỉ số phụ: lưu lượng đi cùng host/network namespace dễ bị tính lẫn. Nên đo bytes qua ứng dụng hoặc adapter/container riêng. Proxy phải stream đúng cách để so sánh công bằng. Chạy cùng file, concurrency, môi trường, số lần lặp; công bố số đo thô và median/p95 nếu có đủ mẫu. Chưa đo thì dùng bảng “chưa thực hiện”, không chèn % tăng tốc hoặc CPU giảm do suy đoán.

## 6. Câu chốt dùng trong sản phẩm

“Thực nghiệm đánh giá khả năng tách luồng cấp quyền khỏi truyền tệp, giới hạn truy cập theo nhóm và phục hồi phiên bản. S3 là dịch vụ managed; MinIO trong lab là hệ lưu trữ tương thích S3 ở phạm vi API đã kiểm thử. Bản chạy cục bộ không chứng minh SLA, độ bền hoặc khả năng chịu lỗi của một cụm production.”

## 7. Nguồn chính thức

Mã nguồn [S01] đến [S30] được liệt kê đầy đủ dưới đây. Mọi nguồn web được truy cập ngày27/10/2026. Không sử dụng blog bên thứ ba làm bằng chứng kỹ thuật. Nguồn marketing MinIO cũ có thể nói “full compatibility”; phải ưu tiên bảng API/phiên bản thực tế có các ngoại lệ.


- [S01] [Amazon S3 increases the maximum object size to 50 TB](https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-s3-maximum-object-size-50-tb/)
- [S02] [Amazon S3 multipart upload limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html)
- [S03] [Amazon S3 FAQs](https://aws.amazon.com/s3/faqs/)
- [S04] [minio/minio repository and README](https://github.com/minio/minio)
- [S05] [S3 API Compatibility — AIStor](https://docs.min.io/aistor/developers/s3-api-compatibility/)
- [S06] [Data protection in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DataDurability.html)
- [S07] [Understanding and managing Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html)
- [S08] [Amazon S3 Service Level Agreement](https://aws.amazon.com/s3/sla/)
- [S09] [What is Amazon S3? — data consistency model](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html)
- [S10] [Understanding S3 Glacier storage classes for long-term data storage](https://docs.aws.amazon.com/AmazonS3/latest/userguide/glacier-storage-classes.html)
- [S11] [Querying data in place with Amazon S3 Select](https://docs.aws.amazon.com/AmazonS3/latest/userguide/selecting-content-from-objects.html)
- [S12] [Amazon Athena FAQs](https://aws.amazon.com/athena/faqs/)
- [S13] [Best practices design patterns: optimizing Amazon S3 performance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [S14] [Download and upload objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [S15] [FAQ — Establishing guardrails and monitoring for presigned URLs](https://docs.aws.amazon.com/prescriptive-guidance/latest/presigned-url-best-practices/faq.html)
- [S16] [Deleting object versions from a versioning-enabled bucket](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html)
- [S17] [Locking objects with Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [S18] [Working with object metadata](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingMetadata.html)
- [S19] [Tagging your objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-tagging.html)
- [S20] [How S3 Versioning works](https://docs.aws.amazon.com/AmazonS3/latest/userguide/versioning-workflows.html)
- [S21] [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [S22] [Manage event ordering and duplicate events with Amazon S3 Event Notifications](https://aws.amazon.com/blogs/storage/manage-event-ordering-and-duplicate-events-with-amazon-s3-event-notifications/)
- [S23] [Replicating objects within and across Regions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [S24] [Using server-side encryption with Amazon S3 managed keys (SSE-S3)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingServerSideEncryption.html)
- [S25] [Using cross-origin resource sharing (CORS)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/cors.html)
- [S26] [POST Policy](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sigv4-HTTPPOSTConstructPolicy.html)
- [S27] [Uploading and copying objects using multipart upload in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html)
- [S28] [Checking object integrity in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html)
- [S29] [MinIO bucket retention guide](https://github.com/minio/minio/blob/master/docs/bucket/retention/README.md)
- [S30] [Single-drive backend explanation — discussion #18152](https://github.com/minio/minio/discussions/18152)
