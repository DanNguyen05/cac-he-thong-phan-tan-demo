# Demo 8–10 phút — Distributed KV Transaction Lab

## Chuẩn bị

1. Docker Desktop Linux Engine phải hoạt động. Chạy `.\scripts\kv-demo.ps1 -Action up`.
2. `docker compose -p kv-transaction-lab ps --all`: sáu service healthy. Mở http://127.0.0.1:19000/rpc, nhãn **Docker**.
3. `.\scripts\kv-demo.ps1 -Action reset`, `-Action verify`: counter=0, balance A/B=100, inventory=100. Không dùng down -v.
4. Giữ PowerShell ở thư mục dự án để CLI stop/start. Browser zoom 100%, nút Trình chiếu/F11, Esc thoát.
5. Nếu UI ghi **Process · không phải Docker**, đang dùng host runner; không trình bày đó là container nghiệm thu. Xem VERIFICATION.md để biết bằng chứng đã chạy.

## 0:00–0:45 — Kiến trúc và KV thật

Tổng quan cho thấy gateway/coordinator/rpc/A/B/C. Mỗi node riêng process/database/volume. Mở GET/PUT, node rpc, key `hello`, value `world`, nhấn Ghi KV rồi GET. Đọc trực tiếp bằng HTTP hoặc `/state`. Chỉ gateway được browser dùng; dừng coordinator không làm chết trang.

## 0:45–2:00 — 8.3 RPC

- Chọn **Mất phản hồi + retry**, Run.
- Chỉ rõ cùng request ID: server đã commit, app client bỏ response, timeout, retry.
- Kết quả **2 attempts / 1 executions**, counter tăng đúng 1. Con số lấy từ actual execution log và HTTP GET.

```powershell
Invoke-RestMethod http://127.0.0.1:19002/kv/counter
.\scripts\kv-demo.ps1 -Action stop -Service rpc
# Dashboard vẫn sống, rpc health đỏ. GET qua gateway trả 503.
.\scripts\kv-demo.ps1 -Action start -Service rpc
Invoke-RestMethod http://127.0.0.1:19002/kv/counter
```

Giải thích: chống thực thi trùng trong phạm vi stable ID + durable dedup; không khẳng định exactly-once tổng quát. Lost response là fault tầng ứng dụng; stop service là lỗi process/container thật. Trước demo kế tiếp hãy chờ mọi health xanh; không auto restart trong dashboard.

## 2:00–3:00 — 8.4 NACK/FIFO

Chọn **B mất #2 → NACK → truyền lại**, Run. B nhận #1 rồi #3, chưa deliver #3; gửi NACK [2]. Sender đọc history và gửi HTTP #2. Cuối cùng A/B/C deliver **1 · 2 · 3**. Xem tất cả → lọc NACK/RETRANSMIT; JSON có source B, target, stream và sequence.

Nhấn mạnh: reliable FIFO trong nhóm cố định, không phải atomic multicast/total order.

Nếu có thời gian, stop participant-b trước Run; kết quả PARTIAL chỉ rõ B. Start B, nhấn **Catch-up Node B** để lấy history, kiểm chứng đủ sequence. Không giả vờ receiver offline đã nhận.

## 3:00–4:00 — 8.5 COMMIT và ABORT

Chọn **Chuyển 10: A → B**, Run. PREPARE → YES → durable COMMIT → ACK. A=90, B=110, C=transaction ID. Global result chỉ verified khi đủ ACK + GET.

Reset khi mọi service sống, rồi **B bỏ phiếu NO**, Run. Decision ABORT, A/B vẫn 100, C vẫn none; locks giải phóng. COMPLETED không đồng nghĩa COMMIT.

## 4:00–6:30 — Trọng tâm: crash sau PREPARED

1. Reset, chọn **Dừng sau PREPARED**, Run tự dừng tại `PAUSED_AFTER_PREPARE`.
2. Node A/B/C **PREPARED**, proposed writes chưa vào KV, balances vẫn 100. Coordinator decision còn null.

```powershell
Invoke-RestMethod http://127.0.0.1:19001/state | ConvertTo-Json -Depth 12
.\scripts\kv-demo.ps1 -Action stop -Service coordinator
docker compose -p kv-transaction-lab ps --all
```

3. Coordinator thực sự stopped; trang vẫn cập nhật. Participant PREPARED, **BLOCKED**, key balance locked. Không participant nào tự chọn COMMIT/ABORT.
4. Có thể thử PUT balance tại A: 409. Đọc balances vẫn 100.

```powershell
.\scripts\kv-demo.ps1 -Action start -Service coordinator
.\scripts\kv-demo.ps1 -Action verify
```

5. Boot ID mới, Coordinator đọc log. **Chưa có durable decision → ABORT**, gửi A/B/C, unlock, GET A/B=100. Đây là recovery của authority sau restart; timeout ở participant không tự giải quyết blocking.

## 6:30–7:30 — Crash sau durable COMMIT

Reset, chọn **Dừng sau durable COMMIT**, Run. Điểm dừng: COMMIT đã ghi disk, A đã nhận (90), B/C còn PREPARED. Global chưa verified.

```powershell
.\scripts\kv-demo.ps1 -Action crash -Service coordinator
.\scripts\kv-demo.ps1 -Action start -Service coordinator
```

Recovery phát lại **cùng COMMIT**, không đổi ABORT: B=110, C=transaction ID, tất cả ACK. So sánh hai crash points để giải thích vai trò durable decision.

## 7:30–9:00 — 8.6 Recovery 100 → 95

Chọn **Crash container → recovery 95**, Run. Setup inventory=100, checkpoint 100, ghi redo -3/-2 → 95. Chờ lời nhắc crash/restart, không chỉ nhấn animation.

```powershell
Invoke-RestMethod http://127.0.0.1:19003/kv/inventory
.\scripts\kv-demo.ps1 -Action crash -Service participant-a
docker compose -p kv-transaction-lab ps --all
.\scripts\kv-demo.ps1 -Action start -Service participant-a
Invoke-RestMethod http://127.0.0.1:19003/state | ConvertTo-Json -Depth 12
Invoke-RestMethod http://127.0.0.1:19003/kv/inventory
```

Node boot ID đổi, recovery report checkpoint=100, replay đúng hai operation, **inventory=95**. Trong Cài đặt → Trạng thái & nguyên lý xem operation nào replay.

```powershell
Invoke-RestMethod -Method Post -Body '{}' -ContentType application/json http://127.0.0.1:19003/recover
Invoke-RestMethod -Method Post -Body '{}' -ContentType application/json http://127.0.0.1:19003/recover
# Cả hai vẫn 95, không cộng lại delta lên state hiện tại.
```

Checkpoint này cục bộ, không phải consistent distributed snapshot. SQLite WAL và logical redo là hai tầng khác nhau.

## 9:00–10:00 — 8.7 Kết luận và bằng chứng

Đối chiếu Docker ps, HTTP GET, durable journal/SQLite và UI. Replay log có nhãn **REPLAY**, chỉ phát lại sự kiện cũ; không chạy thí nghiệm mới. Tóm tắt: dedup không phải general exactly-once; ACK/NACK không phải atomic multicast; 2PC có blocking; recovery đúng cần log/checkpoint bền vững.

## Tình huống bổ sung và phục hồi môi trường

- Participant PREPARED crash: scenario tương ứng, chờ PREPARED, stop participant-b, nhấn Bước tiếp. Coordinator ghi COMMIT, DECISION_PENDING; start B, nó giữ PREPARED từ volume rồi nhận COMMIT retry.
- Recreate volume proof: PUT key `proof`, `docker compose -p kv-transaction-lab up -d --no-deps --force-recreate participant-a`, chờ health, GET proof vẫn còn. Không xóa volume.
- Nếu còn in-doubt tx: start tất cả service, chờ coordinator recovery/ACK; Reset từ chối heuristic xóa PREPARED. Nếu HTTP offline, xác minh Docker ps/logs trước.
- Kết thúc: `.\scripts\kv-demo.ps1 -Action down` giữ volumes. Lần sau up rồi Reset chủ động khi các tx đã hoàn tất.
- Docker/WSL chưa hoạt động: không tuyên bố demo container thành công. Có thể chạy host mode để chứng minh logic, nhưng nghiệm thu Docker volume/network vẫn còn riêng.


## Doi chieu SQLite trong dung container

```powershell
docker compose -p kv-transaction-lab exec -T participant-a python -c "import sqlite3; c=sqlite3.connect('/data/kv-A.sqlite'); print(c.execute('SELECT key,value FROM kv').fetchall()); print(c.execute('SELECT * FROM checkpoints').fetchall()); print(c.execute('SELECT * FROM redo ORDER BY lsn').fetchall())"
docker compose -p kv-transaction-lab exec -T coordinator python -c "import sqlite3; c=sqlite3.connect('/data/kv-coordinator.sqlite'); print(c.execute('SELECT id,phase,decision,votes,acks FROM distributed_tx').fetchall())"
```

Cac lenh tren la buoc nghiem thu Docker thu cong khi Engine hoat dong; chua duoc bao la da chay trong moi truong Engine loi. Journal ben vung nam trong bang journal cua tung database. So sanh time/run_id/transaction ID voi HTTP /state va UI.
