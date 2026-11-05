# Hợp đồng API

Base URL mặc định `http://127.0.0.1:8000`. JSON UTF-8. Mọi endpoint quản trị chỉ dành cho máy cục bộ. Swagger của Supervisor ở `/docs`; Coordinator ở `:8001/docs`; node ở `:8101/docs`, `:8102/docs`, `:8103/docs`. HTTP 409 biểu thị xung đột lifecycle/giao thức, 422 là đầu vào không hợp lệ, 503 là dịch vụ không khả dụng.

## Supervisor / frontend API

| Method | Endpoint | Response / hành vi |
|---|---|---|
| GET | `/api/health` | `{service,pid,processes:{coordinator,A,B,C:{alive,pid,port}}}` |
| GET | `/api/catalog` | `{rpc,group,commit,recovery}`; mỗi mục là danh sách `[scenario_id,title_vi,description_vi]` |
| GET | `/api/state` | Snapshot `{run,events,nodes,services,transactions}` |
| GET | `/api/events` | SSE, named event `snapshot`, payload giống `/api/state`, chu kỳ khoảng 450 ms |
| POST | `/api/runs` | Bắt đầu tác vụ async, trả `{id}`; 409 nếu run cũ chưa kết thúc hoặc transaction chưa xử lý |
| POST | `/api/step` | Cho phép hành động backend tiếp theo; `{step:true}` |
| POST | `/api/reset` | Hủy worker, restart process thiếu, xóa toàn bộ state thí nghiệm; `{reset:true}` |
| POST | `/api/resolve` | Restart process thiếu và tiếp tục durable decision; `{resolving:tx_id,decision}` |
| POST | `/api/process/{target}/{action}` | `target=coordinator,A,B,C`; `action=crash,restart,unavailable,available`. Coordinator chỉ hỗ trợ crash/restart |

`/internal/process/{target}/{action}` là callback HTTP local từ Coordinator tới Supervisor để thực thi crash/restart node. Body bắt buộc `{run_id}`; ID cũ sau reset/completion bị từ chối 409. Không có auth vì toàn bộ service bind loopback; không mở ra mạng công cộng.

### Tạo run

```json
{
  "module": "rpc",
  "scenario": "lost_response",
  "mode": "step",
  "deduplicate": true,
  "retry": true,
  "max_attempts": 3,
  "target": "B",
  "delay_ms": 0
}
```

- `module`: `rpc|group|commit|recovery`, bắt buộc.
- `scenario`: lấy từ catalog, mặc định `normal`. Scenario ID phải thuộc module tương ứng.
- `mode`: `auto|step`, mặc định `auto`.
- `deduplicate`, `retry`: boolean, mặc định true; chỉ có tác dụng RPC.
- `max_attempts`: integer 1–5, mặc định 3. RPC: tổng số lần gửi; multicast: số vòng; 2PC: số lần gửi quyết định cho mỗi participant. PREPARE không retry trong phiên bản này.
- `target`: `A|B|C`, mặc định B; recipient lỗi hoặc participant lỗi/NO.
- `delay_ms`: integer 0–1500. RPC: lần gửi đầu; multicast: vòng đầu; 2PC: PREPARE. Recovery không áp dụng tùy chọn này. Kịch bản RPC `delay` buộc trễ ít nhất 1000 ms.

Coordinator trả run ID ngay sau khi tạo background task; kết quả cuối lấy qua SSE/state. Status: `RUNNING`, `WAITING`, `COMPLETED`, `FAILED`, `PARTIAL`, `BLOCKED`, `DECISION_PENDING`, `INTERRUPTED`. `COMPLETED` có thể là transaction ABORT hợp lệ; đọc trường `result.decision` để phân biệt quyết định với việc thực thi protocol thành công.

### Snapshot

`run` chứa ID, module, scenario, status, config, created Unix timestamp, result nullable. `result` khác nhau theo protocol, luôn kèm explanation tiếng Việt khi có kết quả cuối.

Mỗi event: `{seq,run_id,time,source,target,kind,detail,data}`. `data` có thể chứa `message_id` (từng lần gửi), `operation_id` (giữ nguyên qua retry), `attempt`, `path`, `response`, `transaction_id`. Snapshot giới hạn 600 event gần nhất của run hiện tại; database giữ event đầy đủ tới Reset. Không dùng SSE `Last-Event-ID`: reconnect gửi full snapshot hiện tại, nên UI thay thế state thay vì nối lặp sự kiện.

`nodes` chứa state đọc HTTP trực tiếp từ A/B/C. Node chết: `{node,available:false,crashed:true}`; UI không tái sử dụng counter cũ như dữ liệu live. Unavailable: process còn sống, `available:false`, các counter vẫn đọc được. `services` lấy từ child-process handles, độc lập với availability.

## Participant API

| Method | Path | JSON body | Kết quả |
|---|---|---|---|
| GET | `/health` | — | `{node,pid,available}` |
| GET | `/state` | — | Counters, checkpoint, operations, transactions, receipts, recovery report, 60 log entries gần nhất |
| POST | `/rpc` | `{id,deduplicate:true,delta:1}` | `{id,value,execution_count,duplicate}` |
| POST | `/multicast` | `{id,payload}` | `{id,ack,duplicate,delivery_count}` |
| POST | `/prepare` | `{id,amount:10,vote_no:false}` | `{id,vote:"YES"|"NO",state}` |
| POST | `/decision` | `{id,decision:"COMMIT"|"ABORT"}` | `{id,state,duplicate}`; mâu thuẫn hoặc COMMIT không PREPARED trả 409 |
| POST | `/operation` | `{id,delta:5}` | `{id,value,duplicate}` |
| POST | `/checkpoint` | `{}` | `{seq,value}` |
| POST | `/recover` | `{}` | `{checkpoint_seq,checkpoint_value,replayed,value,pid}` |
| POST | `/availability` | `{available:false}` | Health state; không giết process |
| POST | `/reset` | `{}` | Xóa toàn bộ protocol state node, `{reset:node_name}` |

Protocol endpoints trả 503 nếu node bị đánh dấu unavailable; health/state/availability/reset vẫn truy cập được. ID do Coordinator tạo từ UUID; mỗi operation/message thuộc run được định danh bền vững.

## Ví dụ PowerShell

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
$body = @{module='commit'; scenario='coordinator_crash'; mode='auto'} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/runs -Method Post -ContentType 'application/json' -Body $body
# Khi run BLOCKED:
Invoke-RestMethod http://127.0.0.1:8000/api/state
Invoke-RestMethod http://127.0.0.1:8000/api/resolve -Method Post
```


## Bổ sung v2 (tương thích endpoint cũ)

- Run config nhận thêm `pace_ms: 0..3000` (mặc định LAB_PACE × 1000) và `paused: boolean`.
- POST /api/control với `{paused?: boolean, pace_ms?: number}` cập nhật worker đang chạy; trả `{paused,pace_ms}`. 409 nếu không có worker hoặc yêu cầu pause/resume trong step mode. Thay đổi được phản ánh ở run.config qua SSE.
- Pause dừng ở ranh giới hành động; lệnh đang gửi có thể hoàn tất. Next hoạt động khi pause, vẫn giữ trạng thái paused ở gate kế tiếp. Resume auto tiếp tục từ gate hiện tại. Pacing không thay đổi deadline transport hoặc quyết định giao thức.
- GET /healthz trả liveness tối thiểu; GET /readyz trả 200/503 theo trạng thái bốn process.
- Các route giao diện có SPA fallback; API/assets không tồn tại vẫn trả 404.
- LAB_PUBLIC yêu cầu gateway token server-only; /api, UI và docs đều được bảo vệ. Manual process control mặc định 403. Callback /internal cần internal token trong public mode. Xem DEPLOYMENT.md.
- Origin ngoài danh sách cho phép bị từ chối khi mutation. CORS chỉ cho origin khai báo rõ ràng và hỗ trợ credential cookies.
