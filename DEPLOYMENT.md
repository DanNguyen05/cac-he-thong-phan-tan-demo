# Triển khai Docker / local classroom

## Phạm vi hỗ trợ

KV deployment hiện dành cho máy cá nhân/lớp học đáng tin cậy. Sáu port 19000–19005 chỉ publish 127.0.0.1, Docker network internal, volumes riêng. Không có auth/OIDC trong gateway KV. **Không mở port ra Internet hoặc đổi bind 0.0.0.0 trên host để public demo.** Các template public gateway của phiên legacy trong deploy/ chưa được nghiệm thu với KV mới.

## Build và chạy

```powershell
docker info
docker compose -p kv-transaction-lab config --quiet
docker compose -p kv-transaction-lab up -d --build --wait
docker compose -p kv-transaction-lab ps --all
```

Dockerfile multi-stage build frontend bằng Node 22, runtime Python 3.11, user UID10001. Image dùng chung nhưng mỗi container có KV_SERVICE/LAB_DATA riêng trong volume. Uvicorn một worker/service; không dùng --reload hoặc nhiều workers cho coordinator/gateway.

Compose không đặt dependency làm dashboard restart/stop theo coordinator. Dashboard kiểm tra HTTP và tự nối lại. Coordinator startup tự recover từ durable log; gateway startup không chạy lại RPC không rõ kết quả. Worker/coordinator restart=no để lỗi còn quan sát được; dashboard unless-stopped.

Named volumes: gateway-data, coordinator-data, rpc-data, a-data, b-data, c-data thuộc project kv-transaction-lab. Không mount Docker socket, không dùng privileged containers. Docker commands chỉ chạy bởi người trình bày/script cục bộ.

## Data và ports

Lần đầu có dữ liệu khởi tạo xác định. Reset API có kiểm tra live services và PREPARED locks, không xóa volumes. `docker compose down` giữ volumes; **không down -v** để nghiệm thu recovery. Không xóa coordinator volume khi participant còn PREPARED.

Host port đã chọn 19000–19005 để tránh 18001–18005. Script up kiểm tra trước khi tạo project mới, không kill app khác nếu xung đột. Có thể sửa host port trong Compose nếu cần; container DNS/8000 giữ nguyên. Chạy test Docker trên project/demo data dùng riêng vì acceptance có reset/crash/recreate.

## Chẩn đoán Engine

Lỗi ghi nhận trong môi trường hiện tại: pipe dockerDesktopLinuxEngine không tồn tại; backend Desktop báo `listing WSL distros ... context deadline exceeded` khi `wsl.exe -l -v --all`. Docker CLI/Compose có sẵn nhưng image build/container/volume tests chưa thể xác minh khi Engine chưa chạy.

Kiểm tra Docker Desktop và trạng thái WSL trong terminal của máy. Không tự reset/unregister distribution hoặc xóa Docker data. Restart WSL/Windows có thể ảnh hưởng ứng dụng khác, cần người vận hành quyết định. Sau khi Engine trả docker info thành công, up --build --wait rồi chạy KV_TEST_MODE=docker acceptance.

## Development và host fallback

```powershell
python scripts/kv_local.py
# Sáu process thật ở 19100–19105, SQLite riêng; không phải Docker.
cd frontend
$env:LAB_API_URL='http://127.0.0.1:19100'
npm run dev
```

Frontend production phục vụ cùng gateway và hỗ trợ SPA deep links. Env frontend VITE_API_URL/VITE_SSE_URL được dùng bởi adapter hiện có; không nhúng secrets. Cấu hình gateway KV chấp nhận localhost development origins cụ thể; không wildcard. Backend Docker tự cấu hình DNS qua KV_COORDINATOR/KV_RPC_SERVER/KV_PEERS.

Nếu cần Internet sau này: triển khai authenticated reverse proxy/TLS, session authorization, allowlist demo; bỏ public worker port mappings, giới hạn admin/fault endpoints, CSRF/rate limits và kiểm tra dependency/security riêng. Static frontend không chạy thay Python/container. Chưa có cloud deployment hoặc nghiệm thu nginx/OIDC cho KV.

Tài liệu deployment legacy: docs/LEGACY_DEPLOYMENT.md.
