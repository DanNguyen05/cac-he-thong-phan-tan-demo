# API Distributed KV Transaction Lab

Compose: gateway `http://127.0.0.1:19000`; coordinator `:19001`; rpc `:19002`; A/B/C `:19003/19004/19005`. Local process runner dùng base 19100. JSON UTF-8. Local trusted demo; không có Internet authentication. Swagger `/docs` từng service.

## Gateway

| Method | Path | Hành vi |
|---|---|---|
| GET | /health, /healthz | Gateway sống độc lập worker |
| GET | /api/health | HTTP health thực của năm service bên dưới, boot ID, observed_at |
| GET | /api/state | run/events/nodes/services/transactions/runtime, tương thích frontend hiện có |
| GET | /api/events | SSE named `snapshot`, khoảng 450ms, reconnect đọc snapshot; không nối giả event |
| GET | /api/catalog | Các scenario hợp lệ theo module |
| POST | /api/runs | Chạy demo có orchestration backend thật |
| POST | /api/step | Cho qua boundary đang WAITING; không phải step animation |
| POST | /api/control | paused hoặc pace_ms tại boundary, không thay timeout network |
| POST | /api/reset | Reset demo qua HTTP, giữ volume; từ chối service offline/PREPARED |
| POST | /api/resolve | Xem coordinator recovery; không start container |
| GET | /api/kv/{node}/{key} | Proxy GET tới worker rpc/A/B/C |
| POST | /api/kv/{node} | Proxy ghi KV; không ghi thủ công khi run đang active |
| POST | /api/transactions | Giao dịch tùy chỉnh, được gắn vào dashboard run |
| GET | /api/transactions/{id} | Durable transaction của coordinator |
| POST | /api/group/catchup | target và stream; retransmit history tới receiver đã restart |
| POST | /api/process/{target}/{action} | Luôn 403 trong KV: dùng Docker CLI cục bộ |

```json
{"module":"commit","scenario":"coordinator_crash","mode":"auto","pace_ms":300,"target":"B"}
```

RunConfig: module rpc/group/commit/recovery; scenario từ catalog; mode auto/step; pace_ms 0–3000; target A/B/C; deduplicate/retry boolean; max_attempts 1–5 cho RPC. delay_ms hiện giữ trong hợp đồng tương thích nhưng không áp dụng trong KV; UI KV ẩn tùy chọn này. Lost fault là policy xác định theo scenario, không random.

Status: RUNNING, WAITING, COMPLETED, FAILED, PARTIAL, BLOCKED, DECISION_PENDING, INTERRUPTED. COMPLETED với ABORT là protocol đã kết thúc đúng; đọc result.decision. result.verified chỉ true sau đọc HTTP khớp giá trị; chưa complete thì false. `runtime.containerized=false` là host process, không phải Docker.

Event có `seq,time,run_id,source,target,kind,detail,data`; IDs nằm trong data (`request_id`, `transaction_id`, `stream/sequence`, `operation_id`). Node events thu qua HTTP có service/service_seq. Gateway lưu journal riêng; snapshot giới hạn 1200 event hiện tại. `/state` từng worker giữ journal đầy đủ trong phiên demo; quy mô lớp học, chưa phân trang journal/history lớn.

## KV worker (rpc và participant)

| Method | Path | Body / kết quả |
|---|---|---|
| GET | /health | service,node,pid,boot_id,runtime,available |
| GET | /state | KV, locks, tx, group receipt/delivery, operations, checkpoint, recovery, events |
| GET | /kv/{key} | node,key,value,locked; 404 nếu chưa tồn tại |
| POST | /kv | `{id,key,operation:"PUT" hoặc "INCREMENT",value,run_id?,deduplicate?}` |
| POST | /prepare | `{id,run_id,writes,expected?,vote_no?}` → vote/state |
| POST | /decision | `{id,run_id,decision:"COMMIT" hoặc "ABORT"}` |
| POST | /multicast | `{stream,run_id,seq,payload}` → ack,received,delivered,missing |
| POST | /recovery/setup | `{run_id}` → inventory=100, reset redo/checkpoint recovery riêng |
| POST | /operations | `{id,run_id,delta}` → inventory value và duplicate |
| POST | /checkpoint | `{run_id?}` → seq,value |
| POST | /recover | `{run_id?}` → checkpoint metadata, replayed IDs/entries, value |
| POST | /reset | `{}`; từ chối prepared locks, không xóa Docker volume |

PUT/INCREMENT hỗ trợ int/string theo phép ghi, key dài tối đa 80. `inventory` dành riêng redo API, không ghi qua PUT/PREPARE. Request ID hoặc log ID dùng lại với nội dung khác: 409. Key locked: 409. Decision mâu thuẫn hoặc COMMIT chưa PREPARED: 409. 422 là input không hợp lệ.

```powershell
$body=@{id='request-demo-1';key='counter';operation='INCREMENT';value=1} | ConvertTo-Json
Invoke-RestMethod -Method Post -ContentType application/json -Body $body http://127.0.0.1:19002/kv
# Gửi lại cùng body: duplicate=true, counter không tăng lần nữa.
```

## Coordinator

POST `/transactions` nhận id (mặc định UUID), run_id, scenario, mode, target, pace_ms, writes tùy chọn. writes bắt buộc gồm đúng A/B/C, mỗi node có ít nhất một key. Bỏ writes thì đọc balances và tạo A-10/B+10/C transaction ID. Expected values được gửi trong PREPARE để phát hiện dữ liệu thay đổi giữa read và prepare.

```json
{"id":"tx-custom-1","writes":{"A":{"balance":80},"B":{"balance":120},"C":{"last_transaction":"custom-1"}},"scenario":"normal"}
```

GET `/transactions/{id}` và `/state` chứa phase, decision (null trước durable decision), votes, acks, writes, before_values và journal. Phase: PREPARING, READY, PAUSED_AFTER_PREPARE, DECISION_DURABLE, PAUSED_AFTER_COMMIT, DECISION_PENDING, COMPLETE, INTERRUPTED. POST `/step` / `/control` điều khiển boundary. POST `/reset` từ chối transaction chưa complete.

Không có endpoint “tự quyết định tại participant”, “chọn COMMIT tùy ý sau coordinator crash” hoặc “Docker exec”. Decision messages giả định trusted network/client; đây chưa phải public authenticated transaction service.

API legacy giữ nguyên trong backend.manager/node/coordinator và tài liệu docs/LEGACY_API.md.
