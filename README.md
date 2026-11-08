# Distributed KV Transaction Lab

Hướng dẫn nói và thao tác demo 8–10 phút: [HUONG_DAN_THUYET_TRINH.md](HUONG_DAN_THUYET_TRINH.md). File phân biệt rõ Process mode dự phòng và Docker mode cần nghiệm thu, kèm lệnh gây lỗi, kết quả dự kiến và câu hỏi thường gặp.

Đồ án Chương 8, mục **8.3–8.7**, *Distributed Systems, 4th Edition* — van Steen & Tanenbaum. Nâng cấp Fault Tolerance Lab hiện có; giữ chế độ Python legacy, không triển khai Raft/Paxos.

**HTTP thật → xử lý độc lập → lỗi thật → recovery đúng → đọc lại dữ liệu.**

## Chạy bằng Docker Desktop Windows

Yêu cầu Docker Desktop **Linux containers**, Docker Compose v2 và Engine hoạt động. Không cần cloud/API trả phí. Lần build đầu cần Internet tải image/npm/pip.

```powershell
.\kv-start.bat
# Hoặc:
.\scripts\kv-demo.ps1 -Action up
```

Mở **http://127.0.0.1:19000/rpc**. Script build React/TypeScript và Python image, khởi động sáu container, chờ health checks. Engine chưa chạy thì script báo lỗi; không coi đó là khởi động thành công.

```powershell
docker compose -p kv-transaction-lab up -d --build --wait
docker compose -p kv-transaction-lab ps --all
.\scripts\kv-demo.ps1 -Action health
```

Port 19000–19005 chỉ bind **127.0.0.1**; script kiểm tra xung đột khi khởi động mới. Không tác động cổng 18001–18005 của dự án tham khảo.

## Kiến trúc

| Service Compose | Host port | Nhiệm vụ | Volume riêng |
|---|---:|---|---|
| dashboard | 19000 | Web, client RPC, publisher, collector/SSE | gateway-data |
| coordinator | 19001 | 2PC, durable decision, tự recovery khi boot | coordinator-data |
| rpc | 19002 | KV, INCREMENT, durable dedup | rpc-data |
| participant-a | 19003 | KV, 2PC, FIFO multicast, checkpoint/redo | a-data |
| participant-b | 19004 | KV, 2PC, FIFO multicast | b-data |
| participant-c | 19005 | KV, 2PC, FIFO multicast | c-data |

Mỗi service là một Uvicorn process trong container riêng, giao tiếp HTTP qua Docker network. Không dùng chung database hoặc volume. Gateway không spawn container, không mount Docker socket, không chạy shell từ API. Dashboard vẫn sống khi Coordinator/worker không phản hồi.

KV ban đầu: participants có `balance=100`, `last_transaction="none"`, `inventory=100`; RPC có `counter=0`. Transaction mặc định chuyển 10 từ A sang B, C lưu transaction ID.

## Bốn thí nghiệm và tổng kết

| Mục | Thao tác | Bằng chứng |
|---|---|---|
| 8.3 RPC | Normal / mất phản hồi + retry | Cùng request ID, 2 attempts, 1 execution, counter tăng 1; còn sau restart |
| 8.4 Group | HTTP multicast #1–#3, B mất #2 | NACK, history retransmit, FIFO deliver 1,2,3 |
| 8.5 Commit | COMMIT / NO / crash trước-sau decision | PREPARED giữ khóa; không decision thì recovery ABORT; durable COMMIT thì replay COMMIT |
| 8.6 Recovery | Checkpoint 100, redo -3,-2, kill/start | GET inventory=95, replay lại vẫn 95 |
| 8.7 Tổng kết | So sánh giả định | Dedup, delivery, atomic decision và local recovery có bảo đảm khác nhau |

Chọn scenario → **Chạy thí nghiệm** → xem topology/KV → **Đã kiểm chứng bằng HTTP GET**. Chọn **Từng bước** trước Run để dùng **N**; **P** pause/resume tại ranh giới hành động. **Esc** đóng dialog/thoát trình chiếu. Nhập văn bản không kích hoạt shortcut.

**GET / PUT** đọc/ghi worker qua gateway. Key PREPARED trả 409; `inventory` chỉ ghi qua redo API để bảo toàn recovery. **Replay log** chỉ xem timeline đã ghi, không gửi request hoặc tái tạo state quá khứ.

## Gây lỗi thật

```powershell
# Scenario “Dừng sau PREPARED”, Run, chờ PAUSED_AFTER_PREPARE:
.\scripts\kv-demo.ps1 -Action stop -Service coordinator
# Dashboard còn sống, participant PREPARED, giao dịch BLOCKED.
.\scripts\kv-demo.ps1 -Action start -Service coordinator
# Chưa có durable decision => recovery ABORT.

# Recovery “Crash container → recovery 95”, Run, chờ lời nhắc:
.\scripts\kv-demo.ps1 -Action crash -Service participant-a
.\scripts\kv-demo.ps1 -Action start -Service participant-a
.\scripts\kv-demo.ps1 -Action verify
```

Worker/coordinator dùng `restart: "no"` để SIGKILL còn quan sát được tới khi start thủ công. Gateway dùng `unless-stopped`. Không dùng `down -v`. `-Action down` giữ named volumes. Reset qua API chỉ được phép khi mọi service đang sống và không có transaction chưa giải quyết.

## Kiểm chứng trực tiếp

```powershell
Invoke-RestMethod http://127.0.0.1:19002/kv/counter
Invoke-RestMethod http://127.0.0.1:19003/kv/balance
Invoke-RestMethod http://127.0.0.1:19004/kv/balance
Invoke-RestMethod http://127.0.0.1:19003/kv/inventory
Invoke-RestMethod http://127.0.0.1:19001/state | ConvertTo-Json -Depth 12
docker compose -p kv-transaction-lab logs --tail 100 coordinator
```

`/state` từng service chứa durable journal, locks, transactions, redo/checkpoint. SQLite trong `/data/kv-{service}.sqlite`; dùng Python/sqlite3 trong đúng container để đối chiếu. Gateway không đọc file database của các service khác.

## Kiểm thử

```powershell
python -m pip install -r requirements.txt
python -m pytest tests -q
# Mặc định: test legacy + KV bằng sáu process thật, data/port tạm.

# Cùng acceptance KV bằng container/volume thật:
$env:KV_TEST_MODE='docker'
python -m pytest tests/test_kv_lab.py -q
Remove-Item Env:KV_TEST_MODE

cd frontend
npm ci
npm run typecheck
npm run build
# Legacy riêng đang chạy ở LAB_UI_URL, mặc định 8000:
npx playwright test
# KV Docker đang chạy ở 19000:
$env:LAB_UI_URL='http://127.0.0.1:19000'
npx playwright test --config playwright.kv.config.ts
```

**Docker acceptance có reset/crash/recreate container thuộc project `kv-transaction-lab`.** Không chạy trong phiên cần giữ dữ liệu demo. Không xóa volumes hoặc tác động project khác. Engine không chạy thì fixture báo **skipped**, không phải passed. Kết quả thực tế ở [VERIFICATION.md](VERIFICATION.md).

## Khi Docker Engine chưa hoạt động

Có thể nghiệm thu logic bằng sáu process độc lập, vẫn HTTP/database thật:

```powershell
python scripts/kv_local.py
# http://127.0.0.1:19100/rpc — UI ghi rõ Process, không phải Docker.
# Ctrl+C dừng các process con; data/kv-local vẫn giữ.
```

Host mode không chứng minh Docker volume/network/recreate. Lỗi `listing WSL distros ... context deadline exceeded` thuộc Docker Desktop/WSL. Không tự reset/unregister distribution hoặc xóa Docker data. Sau khi Engine hoạt động, chạy lại acceptance Docker.

## Source và chế độ cũ

`backend/kv_common.py`, `kv_node.py`, `kv_coordinator.py`, `kv_gateway.py` là các service mới. `compose.yaml`, `Dockerfile`, `scripts/kv-demo.ps1` cung cấp triển khai. Frontend tái sử dụng layout sáng, React Flow/SVG, shortcuts và presentation; thêm KV workbench/replay.

Backend legacy và `start.bat -SystemPython` vẫn chạy ở 8000. Tài liệu cũ giữ tại [docs/LEGACY_README.md](docs/LEGACY_README.md). Dự án Raft chỉ được đọc để học cách tổ chức, không đưa code của nó vào thuật toán hoặc release mới.

## Giới hạn

Chỉ dành cho **local classroom/trusted demo**, chưa sẵn sàng public Internet. Không có consensus, HA coordinator, Byzantine protection, distributed snapshot, 3PC hay atomic/total-order multicast. Không tuyên bố exactly-once tổng quát. 2PC không cung cấp distributed read snapshot: từng node có thể nhận COMMIT ở thời điểm khác nhau; dashboard chỉ báo hoàn thành khi đủ ACK và GET xác minh. Xem [ARCHITECTURE.md](ARCHITECTURE.md), [API.md](API.md), [DEMO_GUIDE.md](DEMO_GUIDE.md) cho giả định và kịch bản 8–10 phút.
