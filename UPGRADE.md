# Nâng cấp Distributed KV Transaction Lab

Đây là nâng cấp dự án hiện có, không thay dự án khác hoặc triển khai Raft. Backend legacy giữ nguyên; các service KV mới sử dụng lại FastAPI/httpx, SQLite primitives và frontend React Flow/SVG.

## Tệp chính

| Phần | Tệp |
|---|---|
| KV storage/worker | backend/kv_common.py, backend/kv_node.py |
| Transaction authority | backend/kv_coordinator.py |
| Gateway/client/publisher/collector | backend/kv_gateway.py |
| Docker | compose.yaml, Dockerfile, .dockerignore |
| Windows và fallback | scripts/kv-demo.ps1, kv-start.bat, scripts/kv_local.py |
| Giao diện | frontend/src/KVWorkbench.tsx, App.tsx, useLab.ts, types.ts, topology.ts, LabSummary.tsx, ReactFlowDiagram.tsx, OfflineDiagram.tsx, style.css |
| Regression | tests/test_kv_lab.py, frontend/e2e/kv.spec.ts, kv-fault.spec.ts, playwright.kv.config.ts, playwright.config.ts |
| Đóng gói | scripts/package.py, release/fault-tolerance-lab.zip |
| Tài liệu | README/API/ARCHITECTURE/DEMO_GUIDE/DEPLOYMENT/VERIFICATION, design-system; docs/LEGACY_* giữ bản cũ |

Các thuật toán/backend legacy và start.bat không bị thay đổi. Không migration hoặc xóa database cũ. Docker dùng volumes và database tên kv-* riêng. Dự án tham khảo trong raft-kv-store-phamthehiep chỉ đọc, được loại khỏi .gitignore tracking và package.

## Tính năng mới

- Sáu service/container độc lập, HTTP và persistent volumes riêng, gateway không phụ thuộc lifecycle coordinator.
- KV GET/PUT/INCREMENT, request fingerprint, durable dedup, mất response ở app transport và retry cùng ID.
- HTTP multicast ba message, sequence gap, NACK, FIFO buffer, history và catch-up có chủ đích.
- 2PC chuyển tiền A→B và metadata C; PREPARED/locks bền vững, expected values, durable COMMIT/ABORT, retry ACK.
- Điểm dừng trước decision và sau COMMIT; CLI dừng container thật, coordinator startup presumed-abort hoặc replay durable decision.
- Inventory checkpoint 100, redo -3/-2, restart/replay về 95, replay idempotent và event ID conflict protection.
- Dashboard số liệu/KV thật, GET/PUT editor, external fault instructions, health/boot ID, verified result và replay log gắn nhãn rõ.
- Docker lifecycle chỉ ở CLI cục bộ, không socket hoặc shell trong API. Reset không tự restart node hoặc xóa PREPARED.

## Nghiệm thu

Xem VERIFICATION.md. Process tests chứng minh logic và lỗi process thật; không thay thế Docker acceptance. Engine hiện tại có lỗi WSL nên không tuyên bố build/container/volume đã chạy thành công. Image/Compose và scripts đã chuẩn bị để chạy lại acceptance khi Engine hoạt động.

Chạy Docker: kv-start.bat → http://127.0.0.1:19000/rpc. Host fallback: python scripts/kv_local.py → http://127.0.0.1:19100/rpc, nhãn Process rõ ràng. Legacy: start.bat -SystemPython → 8000.
