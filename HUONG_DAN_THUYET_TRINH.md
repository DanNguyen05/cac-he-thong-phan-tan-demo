# Hướng dẫn thuyết trình — Distributed KV Transaction Lab

Mục tiêu: trình bày **request thật → xử lý trên các node độc lập → gây lỗi → khôi phục → kiểm chứng dữ liệu** trong khoảng 8–10 phút. Phạm vi Chương 8: 8.3 RPC, 8.4 Group Communication, 8.5 Distributed Commit, 8.6 Recovery và 8.7 tổng kết.

## 1. Bản web đang chạy trên máy

- Địa chỉ: **http://127.0.0.1:19100/rpc**.
- Chế độ hiện tại: **Process · không phải Docker**. Có sáu tiến trình Python riêng, giao tiếp HTTP, mỗi service lưu SQLite riêng trong `data/kv-local/<service>/`.
- Docker Engine chưa kết nối được khi chuẩn bị tài liệu ngày 08/11/2026. Không nói rằng bản đang mở chạy bằng container.
- **Docker vẫn là phương án nghiệm thu theo yêu cầu đồ án.** Process mode là bản dự phòng để xem web và kiểm chứng HTTP/giao thức/storage; chưa thay thế bằng chứng container độc lập, Docker network và dữ liệu giữ qua Docker volume/recreate.
- Frontend đã build thành công. Việc kiểm tra health lúc khởi động không thay thế kiểm thử toàn bộ kịch bản lỗi.

| Service | Process mode đang mở | Docker mode khi Engine hoạt động |
|---|---|---|
| Dashboard / gateway | 19100 | 19000 |
| Coordinator | 19101 | 19001 |
| RPC Server | 19102 | 19002 |
| Participant A | 19103 | 19003 |
| Participant B | 19104 | 19004 |
| Participant C | 19105 | 19005 |

**Chỉ chọn một chế độ và dùng đúng cổng/lệnh của chế độ đó trong suốt bài demo.** Dashboard hiển thị lệnh Docker khi chạy Docker mode; Process mode hướng dẫn dùng PowerShell theo mục 4. Không chạy lệnh Docker để điều khiển các process tại cổng 19100–19105.

## 2. Chuẩn bị trước khi vào lớp

Mở PowerShell tại thư mục dự án:

```powershell
Set-Location D:\He_Thong_Phan_Tan\demo_cachethong
```

Nếu web Process mode chưa chạy:

```powershell
python scripts/kv_local.py
# Giữ terminal này mở. Dashboard: http://127.0.0.1:19100/rpc
```

Không chạy thêm runner nếu sáu service đã chạy. Kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:19100/api/health | ConvertTo-Json -Depth 6
```

`processes` phải có coordinator, rpc, A, B, C với `alive=true`; gateway chính là service trả response. Nếu mọi node đã online và không còn giao dịch chờ quyết định, nhấn **Đặt lại** để về dữ liệu ban đầu. Reset chủ động xóa dữ liệu thử nghiệm, không dùng khi đang muốn giữ bằng chứng của lần chạy trước.

Checklist trước khi trình bày:

- Đọc file này và tập ít nhất một vòng hoàn chỉnh, đặc biệt hai điểm dừng của Coordinator.
- Đóng ứng dụng nặng, bảo đảm ổ C còn dung lượng cho trình duyệt/paging file. Máy đã từng hết ổ C và không khởi động được tiến trình kiểm thử.
- Mở trình duyệt zoom 100%, nhấn **Trình chiếu**; có thể dùng F11. **Esc** đóng hộp thoại hoặc thoát trình chiếu của ứng dụng; F11 để thoát fullscreen trình duyệt.
- Để tốc độ **1×**; dùng 0.5× khi giải thích. Tốc độ không phải mô phỏng latency mạng có đo đạc.
- Để sẵn terminal đọc KV và terminal gây lỗi. Không chạy bộ acceptance test trong phiên demo vì test có thể reset dữ liệu.
- Dùng **Từng bước trước khi Run** nếu cần trình bày chậm. **N** tiếp bước, **P** tạm dừng/tiếp tục tại ranh giới backend hỗ trợ. Khi chờ lỗi bên ngoài, phải dừng/restart node thật; N không thay thế thao tác đó.

## 3. Kịch bản nói và thao tác trong 8–10 phút

### 0:00–0:45 — Tổng quan

**Nói:** “Nhóm em dùng một KV Store để minh họa khả năng chịu lỗi. Dashboard là gateway; RPC Server, Coordinator và ba Participant là các tiến trình độc lập. Dữ liệu và nhật ký được lưu riêng, không lấy số mẫu từ frontend.”

**Làm:** mở **Tổng quan**, chỉ topology và trạng thái online. Nhấn **GET / PUT**, chọn node `rpc`, key `hello`, phép ghi `PUT`, value `world`; nhấn **Ghi KV**, sau đó **GET**. Đây là thao tác ghi dữ liệu thật; không sử dụng key `counter` cho phần chào đầu để khỏi làm lệch phép đếm RPC.

### 0:45–2:00 — 8.3: Mất phản hồi nhưng không thực thi trùng

1. Vào **8.3 Client–Server**. Nhấn **Đặt lại** khi hệ thống sẵn sàng.
2. Chọn **Mất phản hồi + retry** → **Chạy thí nghiệm**.
3. Chỉ trên timeline: request có ID → server thực thi → client bỏ phản hồi → timeout → retry **cùng ID** → server trả kết quả đã lưu.
4. Chỉ kết quả **2 attempts / 1 executions** và `counter=1` sau reset.

```powershell
Invoke-RestMethod http://127.0.0.1:19102/kv/counter
```

**Nói:** “Hai lần gửi nhưng một lần thực thi. Request ID và kết quả dedup được lưu bền vững. Đây là chống thực thi trùng trong phạm vi cơ chế đã cài, không phải bảo đảm exactly-once tổng quát.”

**Phân biệt:** mất response là lỗi tiêm ở tầng ứng dụng; server không bị dừng trong kịch bản này.

### 2:00–3:00 — 8.4: NACK và truyền lại

1. Vào **8.4 Group Comm.**.
2. Chọn **B mất #2 → NACK → truyền lại** → **Chạy thí nghiệm**.
3. B nhận #1 và #3, phát hiện thiếu #2. Chỉ NACK và thông điệp truyền lại từ history.
4. Kết quả A/B/C đều deliver **1 · 2 · 3**; B giữ #3 chờ #2 để bảo đảm FIFO.

**Nói:** “Sender gửi HTTP đến từng receiver. Khoảng trống sequence làm B yêu cầu gửi lại. Đây là reliable FIFO multicast trong nhóm cố định; chưa phải atomic multicast hay total ordering giữa nhiều sender.”

Nếu cần chứng minh sâu hơn, mở nhật ký đầy đủ, chọn event NACK để xem nguồn, đích, stream ID và sequence.

### 3:00–4:00 — 8.5: COMMIT và ABORT

1. **Đặt lại**, vào **8.5 Distributed Commit**.
2. Chọn **Chuyển 10: A → B** → Run. Chỉ PREPARE → YES → quyết định COMMIT ghi bền vững → gửi quyết định → ACK.
3. Sau khi xác minh: **A=90, B=110**, C lưu transaction ID.
4. **Đặt lại**, chọn **B bỏ phiếu NO** → Run. Kết quả ABORT, **A=B=100**, C vẫn `none`.

**Nói:** “Participant ghi PREPARED và giữ khóa trước khi vote YES. Coordinator chỉ COMMIT khi đủ YES. Nếu có NO, các thay đổi chưa commit bị hủy.”

### 4:00–6:00 — Trọng tâm: Coordinator chết sau PREPARED

1. **Đặt lại**, chọn **Dừng sau PREPARED** → Run; chờ `PREPARED · chưa ghi quyết định`.
2. Chỉ ba Participant **PREPARED / LOCKED**; A/B vẫn 100, Coordinator chưa có quyết định cuối.
3. **Dừng Coordinator thật** bằng lệnh đúng chế độ ở mục 4 hoặc 5.
4. Chờ dashboard báo **2PC đang blocking**. Gateway vẫn hoạt động; ba Participant còn sống và chờ quyết định.
5. Đọc trực tiếp trạng thái A để chỉ transaction và locks:

```powershell
Invoke-RestMethod http://127.0.0.1:19103/state | ConvertTo-Json -Depth 10
```

6. **Khởi động lại Coordinator** với đúng thư mục dữ liệu cũ.
7. Sau recovery, kết quả **ABORT**, A/B vẫn 100, khóa được giải phóng.

**Nói:** “Đây là hạn chế blocking của 2PC. Participant đã YES không được tự chọn kết quả theo timeout. Khi Coordinator trở lại, nó đọc nhật ký; tại điểm dừng này chưa có durable decision, nên recovery của Coordinator quyết định ABORT theo giả định đã triển khai.”

### 6:00–7:00 — Đối chiếu: crash sau durable COMMIT

1. Chờ giao dịch trước giải quyết xong rồi **Đặt lại**.
2. Chọn **Dừng sau durable COMMIT** → Run.
3. Chỉ COMMIT đã ghi bền vững; A đã nhận, B/C còn PREPARED. Chưa báo xác minh hoàn tất toàn hệ thống.
4. Dừng rồi khởi động lại Coordinator như mục 4 hoặc 5.
5. Kết quả: phát lại **COMMIT**, A=90, B=110; C có transaction ID, đủ ACK.

**Nói:** “Recovery phải giữ nguyên quyết định COMMIT đã ghi. Hai lần crash có kết quả khác nhau vì thời điểm ghi durable decision khác nhau.”

Lưu ý: `stop` là dừng tiến trình thật, không luôn tương đương mất điện đột ngột. Docker `kill --signal SIGKILL` hoặc kết thúc cưỡng bức process phù hợp hơn khi cần minh họa crash.

### 7:00–9:00 — 8.6: Checkpoint và redo log

1. Vào **8.6 Recovery**, chọn **Crash container → recovery 95** → Run. Trong Process mode tên scenario vẫn như vậy nhưng thao tác là dừng process A, không phải container.
2. Chỉ checkpoint `inventory=100`, hai operation **−3, −2**, giá trị trước crash **95**.
3. Chờ dòng **Đang chờ crash và restart Node A thật**.
4. Dừng A → chờ **OFFLINE** → khởi động lại A cùng dữ liệu.
5. Dashboard báo hoàn thành, GET trực tiếp vẫn **95**:

```powershell
Invoke-RestMethod http://127.0.0.1:19103/kv/inventory
Invoke-RestMethod http://127.0.0.1:19103/state | ConvertTo-Json -Depth 10
```

6. Chỉ `boot_id` mới, checkpoint và danh sách log replay. Nếu cần chứng minh replay không áp dụng trùng:

```powershell
Invoke-RestMethod -Method Post -ContentType application/json -Body '{}' http://127.0.0.1:19103/recover
Invoke-RestMethod -Method Post -ContentType application/json -Body '{}' http://127.0.0.1:19103/recover
Invoke-RestMethod http://127.0.0.1:19103/kv/inventory
# Vẫn 95, không thành 90.
```

**Nói:** “Node dựng lại inventory từ checkpoint rồi replay log có thứ tự. Recovery lặp lại không áp dụng delta hai lần lên giá trị hiện tại. Đây là checkpoint cục bộ, không phải distributed snapshot nhất quán.”

### 9:00–10:00 — Tổng kết 8.7

**Nói:** “Nhóm kiểm chứng qua ba lớp: topology và sự kiện trên dashboard, HTTP GET trực tiếp vào node, và nhật ký/database riêng. RPC cần dedup; multicast cần phát hiện thiếu và truyền lại; 2PC có blocking; recovery cần checkpoint và log bền vững.”

Nếu thiếu thời gian: bỏ GET/PUT mở đầu và rút ngắn multicast; giữ phần Coordinator PREPARED và Recovery.

## 4. Gây lỗi trên bản Process mode đang mở — cổng 19100

Mở **hai terminal riêng**: một cho Coordinator, một cho A. Các lệnh dưới đây chỉ dành cho runner mặc định `data/kv-local`, cổng 19100–19105. Nếu đổi thư mục dữ liệu hoặc cổng, phải sửa tương ứng; không dùng một database mới để giả vờ restart.

### Dừng Coordinator

Chỉ chạy sau khi UI đã tới đúng điểm dừng. Kiểm tra identity từ HTTP trước khi lấy PID:

```powershell
$h = Invoke-RestMethod http://127.0.0.1:19101/health
if ($h.service -ne 'coordinator' -or $h.runtime -ne 'process') { throw 'Sai service/runtime; dung thao tac.' }
Stop-Process -Id $h.pid -Force
```

Đợi UI báo blocking, rồi **trong terminal Coordinator** chạy:

```powershell
Set-Location D:\He_Thong_Phan_Tan\demo_cachethong
$env:KV_RUNTIME='process'
$env:KV_SERVICE='coordinator'
$env:LAB_DATA=Join-Path $PWD 'data/kv-local/coordinator'
$env:KV_COORDINATOR='http://127.0.0.1:19101'
$env:KV_RPC_SERVER='http://127.0.0.1:19102'
$env:KV_PEERS='{"A":"http://127.0.0.1:19103","B":"http://127.0.0.1:19104","C":"http://127.0.0.1:19105"}'
python -m uvicorn backend.kv_coordinator:app --host 127.0.0.1 --port 19101
```

Giữ terminal mở. Nếu cần crash Coordinator lần nữa, dùng terminal điều khiển khác để chạy lệnh dừng phía trên, rồi chạy lại câu lệnh `python -m uvicorn ...` tại terminal Coordinator.

### Dừng và restart Participant A

Chờ scenario Recovery nhắc restart rồi chạy:

```powershell
$h = Invoke-RestMethod http://127.0.0.1:19103/health
if ($h.service -ne 'A' -or $h.runtime -ne 'process') { throw 'Sai service/runtime; dung thao tac.' }
Stop-Process -Id $h.pid -Force
```

Sau khi UI hiện OFFLINE, **trong terminal A** chạy:

```powershell
Set-Location D:\He_Thong_Phan_Tan\demo_cachethong
$env:KV_RUNTIME='process'
$env:KV_SERVICE='A'
$env:LAB_DATA=Join-Path $PWD 'data/kv-local/A'
$env:KV_PEERS='{"A":"http://127.0.0.1:19103","B":"http://127.0.0.1:19104","C":"http://127.0.0.1:19105"}'
python -m uvicorn backend.kv_node:app --host 127.0.0.1 --port 19103
```

Các process khởi động thủ công này không thuộc quyền quản lý của runner ban đầu. Kết thúc buổi demo, **Ctrl+C trong từng terminal khởi động thủ công**, rồi Ctrl+C terminal runner nếu bạn đã mở runner bằng tay. Nếu web do phiên trợ lý mở nền, yêu cầu trợ lý dừng đúng lab; không dùng lệnh kill toàn bộ Python trên máy. Dữ liệu vẫn giữ trên đĩa.

## 5. Lệnh tương đương khi demo bằng Docker

Chỉ dùng khi Docker Desktop **Linux Engine đã hoạt động**:

```powershell
.\scripts\kv-demo.ps1 -Action up
.\scripts\kv-demo.ps1 -Action health
# Mở http://127.0.0.1:19000/rpc, UI phải ghi Docker.
```

Toàn bộ lệnh HTTP ở mục 3 phải đổi **191xx → 190xx**. Thay thao tác dừng/start process ở mục 4 bằng:

```powershell
# 2PC: chờ đúng điểm dừng PREPARED hoặc durable COMMIT
.\scripts\kv-demo.ps1 -Action crash -Service coordinator
docker compose -p kv-transaction-lab ps --all
.\scripts\kv-demo.ps1 -Action start -Service coordinator

# Recovery: chờ UI nhắc crash/restart A
.\scripts\kv-demo.ps1 -Action crash -Service participant-a
.\scripts\kv-demo.ps1 -Action start -Service participant-a
.\scripts\kv-demo.ps1 -Action verify
```

Kết thúc: `.\scripts\kv-demo.ps1 -Action down` giữ volumes. **Không dùng `down -v`**. Các lệnh trên thuộc project `kv-transaction-lab`, không dừng container của dự án Raft.

Docker chưa chạy thành công trên môi trường chuẩn bị tài liệu; cần tập và nghiệm thu lại các lệnh container/volume trên máy trình bày. Đừng đổi nhãn Process thành Docker chỉ để thuyết trình.

## 6. Câu hỏi thầy có thể hỏi

| Câu hỏi | Câu trả lời và bằng chứng ngắn |
|---|---|
| Đây có phải animation cố định? | Không. Mở HTTP `/state`, GET key trực tiếp, dừng node và đối chiếu health. Animation dùng event backend. |
| Mỗi node có dữ liệu riêng không? | Có. Mỗi service có SQLite riêng; Docker dùng volume riêng. Không chia sẻ một DB giữa participants. |
| Retry có thể làm tăng counter hai lần không? | Cùng request ID còn trong durable dedup sẽ trả kết quả đã lưu. ID mới là yêu cầu mới, có thể thực thi thêm. |
| Tại sao PREPARED không tự ABORT khi timeout? | Đã YES nên không được tự mâu thuẫn với quyết định toàn cục có thể đã tồn tại; đây là blocking của 2PC. |
| Coordinator restart luôn ABORT? | Không. Chưa có durable decision thì recovery có thể ABORT theo giả định của lab; đã ghi COMMIT thì phải phát lại COMMIT. |
| Có thấy dữ liệu ở các node đổi đúng một thời điểm không? | Không bảo đảm distributed read snapshot. Participant có thể nhận COMMIT khác thời điểm; UI chỉ xác nhận hoàn tất sau ACK và GET kiểm chứng. |
| Multicast này có atomic/total order không? | Không. Đang chứng minh ACK/NACK, retransmission, dedup và FIFO cho stream. |
| Có phải distributed checkpoint không? | Không. Là checkpoint + redo cục bộ tại A. |
| Khôi phục hai lần có cộng/trừ log hai lần không? | Không. Rebuild từ checkpoint theo log; GET inventory sau hai lần recover vẫn 95. |
| Mất request/response có phải container chết? | Không. Đó là fault tầng ứng dụng; container/process chết được tạo bằng CLI bên ngoài. |

## 7. Khi demo bị kẹt

- **Còn PREPARED/BLOCKED:** khởi động lại đúng Coordinator/Participant với dữ liệu cũ, chờ recovery giải quyết. Không xóa DB hoặc ép reset để che trạng thái chưa rõ.
- **Reset lỗi 409:** có giao dịch chưa giải quyết; phục hồi node trước. **503:** có node chưa online.
- **Run không bấm được:** kiểm tra health và lần chạy đang giữ; đóng modal bằng Esc. Nút Step không gây crash thật.
- **Lần RPC/Group/Recovery cũ bị gián đoạn:** sau khi service online, chọn kịch bản và nhấn Run để chạy lại, không cần Docker hoặc reset dữ liệu. Giao dịch 2PC chưa giải quyết vẫn phải phục hồi trước.
- **Màn hình cũ:** Ctrl+F5. Nếu cần SVG fallback, mở `/rpc?renderer=svg`; khi dùng route khác, thay `/rpc` bằng `/group`, `/commit`, `/recovery`.
- **Replay log:** chỉ phát lại timeline đã ghi, không gửi request và không tái tạo trạng thái node quá khứ. Nêu rõ đang REPLAY nếu dùng.
- **Không đủ thời gian:** trình bày normal COMMIT → PREPARED crash → restart → ABORT → recovery 95. Không nhận xét kết quả khi UI còn chờ xác minh.

Tài liệu kỹ thuật chi tiết: [DEMO_GUIDE.md](DEMO_GUIDE.md), [API.md](API.md), [ARCHITECTURE.md](ARCHITECTURE.md), [VERIFICATION.md](VERIFICATION.md).
