# Kiểm chứng Distributed KV Transaction Lab

Ngày 2026-11-06; Windows, Python 3.11, Node 20.20.2, Edge/Playwright 1.63, React Flow 12.12.1. Tất cả kết quả dưới đây là lệnh thực chạy, không mock kết quả giao thức.

## Kết quả

| Bộ kiểm tra | Kết quả | Artifact cục bộ |
|---|---|---|
| Baseline backend trước sửa | 32 passed | test-results/kv-baseline.xml |
| Baseline browser trước sửa | 18 passed | test-results/kv-baseline-frontend.json |
| Backend cuối: 32 legacy + 24 KV | **56 passed**, 0 failed/skipped, 103.336s | test-results/kv-final-backend.xml |
| KV protocols riêng | 24 passed | test-results/kv-final-protocol.xml |
| Browser React Flow / KV | **8 passed**, 0 flaky/failed/skipped | test-results/kv-frontend-final.json |
| Browser legacy | **18 passed**, 0 flaky/failed/skipped | test-results/kv-legacy-frontend-final.json |
| SVG-only / KV | **8 passed** | test-results/kv-svg-frontend.json |
| SVG-only / legacy | **8 passed** | test-results/kv-svg-legacy.json |
| Browser fault sau chỉnh màu semantic | 1 passed, gồm 5 luồng lỗi/restart thật | test-results/kv-fault-final.json |
| TypeScript strict | npm run typecheck: pass | Chạy trước build production |
| React Flow production | npm run build: pass | Bundle chuẩn dùng cho ZIP |
| SVG-only build | npm run build:offline: pass; bản cuối còn build --outDir dist-offline | Giữ runtime SVG fallback |
| Compose | config --quiet/config JSON: pass | test-results/kv-compose-config.json |
| PowerShell/Python syntax | Parser kv-demo.ps1 và compileall: pass | Không có parse errors |
| Docker image build | **Không đạt do Engine chưa hoạt động** | test-results/kv-docker-build.log |
| Docker integration | **24 skipped**, không tính là passed | test-results/kv-docker-acceptance.xml |

Sau build SVG đã build lại React Flow chuẩn. Source/backend legacy và launcher được so sánh byte với commit trước nâng cấp: 9 file Python legacy + start.bat/scripts/start.ps1 không thay đổi. API legacy được regression-test bằng process/HTTP thật. Có một PendingDeprecationWarning hiện hữu từ starlette/python_multipart; chưa đổi dependency backend.

## Những gì đã chứng minh bằng process thật

Acceptance mặc định khởi động **sáu Uvicorn process độc lập**, sáu địa chỉ HTTP và sáu thư mục SQLite riêng. Kill/start process thực, boot ID mới; không dùng TestClient giả lập node hoặc frontend animation làm bằng chứng.

1. KV GET/PUT/INCREMENT và đọc trực tiếp worker.
2. Lost response: hai attempts, một durable execution, counter tăng một; cùng request ID còn dedup sau restart.
3. RPC worker bị kill, HTTP fail, gateway vẫn sống, dữ liệu còn sau boot mới.
4. Multicast ba message tới ba receiver.
5. B nhận #3 thiếu #2, NACK, retransmit từ history, FIFO deliver 1,2,3.
6. Receiver kill/start và catch-up; catch-up cả sau step-mode run không bị kẹt gate cũ.
7. 2PC COMMIT, A=90/B=110/C=transaction ID, đủ ACK và GET verified.
8. NO → ABORT, không thay đổi một phần dữ liệu, không còn locks.
9. Kill Coordinator sau PREPARED trước decision: gateway còn sống, ba node giữ PREPARED/locks, không tự quyết định. Restart authority → ABORT.
10. Kill sau durable COMMIT và ACK A: B/C còn PREPARED, restart → replay cùng COMMIT.
11. Participant restart trong PREPARED giữ khóa, nhận quyết định khi coordinator trở lại.
12. Checkpoint inventory=100, redo -3/-2, kill/start, GET trực tiếp 95; hai entries replayed.
13. Replay lần nữa vẫn 95, duplicate operation ID không cộng lại; nội dung khác cùng ID bị từ chối.
14. Restart/recreate **process với cùng thư mục** giữ KV; đây chưa phải bằng chứng Docker volume.
15. Gateway health phản ánh HTTP unavailable và API Docker lifecycle trả 403.
16. Reset từ chối offline service hoặc PREPARED, không âm thầm xóa dữ liệu còn live.
17. Stale expected value vote NO, request/transaction ID conflicts, direct PUT inventory bị chặn, CORS origin kiểm tra.

## Browser thực

Đã thao tác GET/PUT, chọn scenario, Run, Step/N, typed input không trigger N/P, presentation/Esc, drag/zoom/inspect React Flow, SVG, modal focus và replay. Replay ghi nhận **không có POST** mới. Kiểm tra cả năm workspace ở 375/768/1024/1440/1920px, không tràn ngang document.

kv-fault.spec.ts tạo sáu process riêng (hoặc opt-in Docker bằng KV_UI_DOCKER=1), thực sự dừng/restart Coordinator ở hai crash point, dừng/restart A để recovery, B để catch-up và rpc để kiểm tra counter giữ nguyên. Browser thấy BLOCKED, PREPARED, OFFLINE, boot ID mới, verified data. Những test này đang chạy **process mode**, nhãn UI ghi rõ không phải Docker.

Đã mở xem screenshot RPC, 2PC/presentation, BLOCKED và Recovery, đồng bộ vùng KV với layout sáng. Đã sửa HEALTH_DOWN thành màu lỗi, NACK là chờ, và dùng đúng service `rpc`/HTTP path `/kv` trong audit, không ghi nhầm participant A.

Ảnh chính: test-results/kv-rpc.png, kv-group.png, kv-commit-presentation.png, kv-crash-before-decision.png, kv-crash-after-decision.png, kv-recovery-offline.png, kv-recovery-restarted.png, kv-rpc-restarted.png.

Các vòng trung gian đã phát hiện readiness reset trả 503 khi worker chưa lên đủ, test chờ group failure quá ngắn và một lỗi catch-up sau step mode; đã sửa và chạy lại. Có một lần Edge báo ERR_INSUFFICIENT_RESOURCES ở vòng legacy; vòng cuối cùng chạy lại sạch 18/18, không bật retry để che lỗi.

## Docker: phần CHƯA được chứng minh

Docker CLI 28.1.1, Compose 2.35.1 có sẵn. Đã thử khởi động Docker Desktop và build thật. Linux Engine pipe không tồn tại. Log Desktop ghi:

`waiting for the VM setup to be ready ... listing WSL distros ... wsl.exe -l -v --all: context deadline exceeded`

Build trả exit 1 ở kết nối dockerDesktopLinuxEngine. Không tự reset WSL/unregister distribution hoặc xóa Docker data vì có thể ảnh hưởng ứng dụng khác.

Compose đã được kiểm tra có đúng sáu services/volumes riêng, loopback host ports, health checks, internal network và không Docker socket. Nhưng **chưa xác minh** image build Linux, DNS/HTTP trên Docker network, UID/permission volume, container health/start/kill/recreate và dữ liệu tồn tại qua Docker volume. Không suy ra chúng thành công từ process tests.

Khi Engine hoạt động:

```powershell
.\scripts\kv-demo.ps1 -Action up
$env:KV_TEST_MODE='docker'
python -m pytest tests/test_kv_lab.py -q
Remove-Item Env:KV_TEST_MODE
cd frontend
$env:LAB_UI_URL='http://127.0.0.1:19000'
$env:KV_UI_DOCKER='1'
npx playwright test --config playwright.kv.config.ts
Remove-Item Env:KV_UI_DOCKER
```

Docker tests chỉ điều khiển project kv-transaction-lab, có reset data/crash/recreate nhưng không down -v. Cần nghiệm thu lại tất cả 24 case, đặc biệt recreate volume và hai crash point Coordinator.

## Giới hạn và bàn giao

Local classroom/trusted demo; KV gateway chưa có auth để public Internet. Một coordinator authority/volume, một phiên demo; không HA/consensus/Byzantine, không distributed snapshot, không 3PC hoặc atomic multicast. Global read snapshot không được bảo đảm trong lúc phân phối COMMIT. Journal/history dành cho quy mô lớp học, chưa có retention/pagination production.

Release được tạo từ source và bundle chuẩn, kiểm tra CRC/source matches. Không kèm node_modules, database, .env riêng, credential, dự án Raft tham khảo hoặc artifact thử nghiệm. Các report/screenshot chỉ ở workspace; kết quả đã tóm tắt trong tài liệu đóng gói. Không có cloud deployment.


## Đối chiếu HTTP và SQLite trực tiếp

Đã chạy lại lost-response trên host preview: HTTP result attempts=2, actual_executions=1; GET counter=1. Truy vấn trực tiếp SQLite RPC cho counter=1, journal RPC_EXECUTED của run đúng một dòng, dedup lưu cached result=1. SQLite của node A trong browser fault harness cho checkpoint=100, hai redo -3/-2 và inventory=95 sau restart. Artifact: test-results/kv-data-verification.json. Đây là bằng chứng host storage, không phải Docker volume.

Chỉ báo thiếu sequence trên dashboard được suy ra từ received rows thực của receiver, không tự tạo success. Kết quả global verified vẫn do backend HTTP verification quyết định. Sau khi bổ sung chỉ báo này, browser multicast được chạy lại riêng và đạt (test-results/kv-multicast-final.json); cả hai production builds cũng được tạo lại.
