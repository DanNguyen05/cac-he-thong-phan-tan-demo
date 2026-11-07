# Kịch bản trình bày trên lớp

## Chuẩn bị (trước giờ học)

1. Chạy `setup.bat` một lần khi có mạng. Chạy `start.bat`; mở http://127.0.0.1:8000.
2. Kiểm tra Tổng quan có **5 tiến trình**: Supervisor, Coordinator, A/B/C. Nhấn Node A: PID khác Coordinator, có database riêng.
3. Giữ cửa sổ terminal Supervisor để Ctrl+C dừng lab sau buổi học. Không refresh tab để reset: refresh chỉ kết nối lại trạng thái backend.
4. Chạy thử `python -m pytest tests -q`. Test dùng port/database riêng, không tác động lab trình bày.
5. Dùng trình duyệt zoom 100%, màn hình ít nhất 1280×800; **nút Trình chiếu** bật trình chiếu, **Esc** thoát. Nếu bundle có nhãn `SVG`, các giao thức vẫn chạy thật; chỉ renderer khác React Flow của build tiêu chuẩn.

Trình tự khuyến nghị: **Tổng quan (1 phút) → RPC (4 phút) → multicast (3 phút) → 2PC (5 phút) → recovery (3 phút)**. Dùng Auto để chạy nhanh; Từng bước khi cần hỏi cả lớp trước một hành động.

## Giao diện demo mới

Luồng chính: **Chọn kịch bản → Chạy thí nghiệm → Xem sơ đồ → Quan sát kết quả**.

Panel bên phải chỉ có kịch bản, Chạy, Từng bước, Đặt lại, tốc độ, fault mode và trạng thái. Chọn **Từng bước** trước khi nhấn Chạy; sau đó dùng **Bước tiếp / N**. Khi auto đang chạy, nút chính chuyển thành **Tạm dừng / Tiếp tục**; phím **P** có cùng tác dụng. Tốc độ **0.5× / 1× / 2×** lần lượt là 1200 / 600 / 300 ms giữa các hành động.

**Cài đặt** (bánh răng trên header) chứa retry/dedup, node gây lỗi, max attempts, transport delay, chọn React Flow/SVG, export và trạng thái chi tiết. **Xem tất cả** mở journal đầy đủ để search/filter/inspect. Nút thông tin ở sơ đồ 2PC mở sequence. Timeline chính chỉ giữ ba sự kiện quan trọng; mọi chỉ số lấy từ backend.

## Điều khiển chung

- Chọn module bên trái → chọn kịch bản → chọn Từng bước nếu cần → **Chạy thí nghiệm**.
- Step mode dừng **trước hành động backend**. **Bước tiếp / N** cho phép một hành động, có thể phát sinh nhiều event HTTP. Trước Next đầu tiên, server chưa thực thi.
- Nhấn node để xem JSON state và PID. Nhấn dòng timeline hoặc mũi tên sequence diagram để xem event gốc. Trong Xem tất cả, tab Thông điệp hiển thị message ID và attempt; Nhật ký node đọc local durable logs.
- Màu xanh lá: thành công; vàng: chờ/PREPARED/timeout; đỏ: lỗi/ABORT; xanh dương: giao tiếp.
- Kịch bản hoàn tất có thể chạy kịch bản mới ngay; node tự làm sạch. Run blocking/pending cần phục hồi hoặc Reset trước.
- Để gây lỗi thủ công trong lúc protocol chạy: chọn Từng bước, Chạy thí nghiệm, mở node inspector để crash/unavailable, rồi Next. Lỗi đặt trước khi Chạy thí nghiệm sẽ bị thao tác làm mới node của kịch bản xóa đi.
- **Reset xóa dữ liệu của cả phòng lab, gồm PREPARED.** Nó không chứng minh tính đúng đắn của recovery và không phải giao thức ABORT. Chỉ dùng để chạy lại thí nghiệm một cách chủ ý.
- Xuất snapshot JSON trong Cài đặt để lưu kết quả. Timeline chỉ giữ 600 event mới nhất trong snapshot.

## 8.3 — Reliable Client–Server Communication

### A. Bình thường

1. Chọn **Client–Server → Giao tiếp bình thường**; giữ retry + dedup bật.
2. Chọn Từng bước, Chạy thí nghiệm. Server execution count vẫn 0.
3. Nhấn Next. Quan sát SEND → DELIVERED → ACK, request ID, attempt 1, counter 1, kết quả thành công.

Giải thích: RPC Client chạy trong process Coordinator, POST tới Node A. Web UI chỉ điều khiển và quan sát.

### B. Mất request

1. Chọn **Mất yêu cầu**, Auto, số lần thử 3; Chạy thí nghiệm.
2. Quan sát REQUEST_LOST → TIMEOUT → RETRY, cùng request ID, attempt 2.
3. Server counter cuối = **1**, không phải 2: request đầu bị loại trước khi tới server.

### C. Mất response — điểm nhấn của phần RPC

1. Chọn **Mất phản hồi**, **tắt Khử trùng lặp**, giữ retry; Chạy thí nghiệm.
2. Node đã thực thi ở lần 1, response bị loại; client timeout và retry.
3. Server counter cuối = **2**. Một ý định client đã thực thi hai lần.
4. Bật lại dedup, chạy cùng kịch bản. Counter cuối = **1**, event DUPLICATE_SUPPRESSED; client nhận lại result bền vững.
5. Tắt retry và chạy Mất phản hồi: run FAILED nhưng server counter = **1**. Thất bại tại client không đồng nghĩa thao tác chưa xảy ra.

Câu hỏi cho lớp: “Client nhìn thấy timeout có suy ra server chưa thực thi được không?” Đáp án: không. At-most-once không bảo đảm thành công; at-least-once cần eventual delivery. Không có lời khẳng định exactly-once tổng quát.

### D. Server unavailable, delay và duplication

- **Server không khả dụng**: Node A sống, health đọc được, protocol trả 503; client kết thúc sau retry budget, counter 0.
- **Phản hồi chậm**: transport trì hoãn ít nhất 1000 ms, vượt deadline mặc định 650 ms; timeout trước khi gửi HTTP ở attempt đầu, retry thành công. Tên kịch bản mô tả sự chậm mà client thấy; implementation cụ thể là delay trước HTTP.
- **Nhân đôi thông điệp**: hai HTTP POST cùng ID; dedup bật → 1 execution, tắt → 2 executions.

## 8.4 — Reliable Group Communication

### A. Tất cả nhận

1. Chọn **Group Communication → Tất cả nhận thành công**, Auto; Chạy thí nghiệm.
2. ACK A/B/C, delivery count mỗi node = **1**. Sender gửi cùng message ID cho ba thành viên.

### B. Mất một message và truyền lại

1. Chọn **Mất thông điệp tại một node**, target **B**, max attempts 3.
2. Bỏ lỡ B ở vòng đầu. A/C nhận và ACK ngay.
3. Quan sát RETRANSMIT **chỉ tới B**. Cuối cùng delivery count đều 1.
4. Lọc timeline từ khóa `RETRANSMIT` để chỉ rõ recipient.

### C. Duplicate và thành viên lỗi

- Chọn **Gửi lặp thông điệp**, target B: transport POST hai lần; B chỉ giao một lần, event DUPLICATE_SUPPRESSED.
- Chọn **Một thành viên không khả dụng**, target C: A/B nhận, C không ACK; run PARTIAL, `missing=[C]`. Không làm giả thành công cho toàn nhóm.

Giới hạn: ACK + retransmit hữu hạn, nhóm cố định, chưa có atomic agreement hay total order. Atomic multicast cần bảo đảm agreement và ordering phù hợp, không chỉ gửi thông điệp giống nhau. Node đã nhận không rollback vì node khác chưa nhận. Sender crash không được tự phục hồi multicast round trong bản demo.

## 8.5 — Distributed Commit

### A. Commit

1. Chọn **Distributed Commit → Tất cả bỏ phiếu YES**, Từng bước.
2. Chạy thí nghiệm, nhấn Next 3 lần: từng participant ghi PREPARED rồi VOTE YES. Counter commit vẫn 0.
3. Coordinator ghi durable COMMIT; Next các bước phase 2 để phân phối quyết định.
4. Kết thúc, A/B/C đều COMMIT, số dư từng node = **10**. Sequence diagram thể hiện thông điệp có thật, nhấn mũi tên để kiểm tra JSON.

Ghi chú: durable-decision event có thể xuất hiện ngay sau bước PREPARE cuối trước khi chờ Next phân phối quyết định. Step boundary là hành động giao thức, không phải từng dòng log riêng.

### B. NO → abort

1. Chọn **Một thành viên bỏ phiếu NO**, target B, Auto.
2. B ghi ABORT cục bộ và trả NO. Coordinator ghi global ABORT rồi gửi A/B/C.
3. Cả ba ABORT, bộ đếm vẫn **0**. Run COMPLETED có nghĩa protocol đã kết thúc đúng, không có nghĩa quyết định COMMIT.

### C. Participant chết trước vote

1. Chọn **Participant chết trước khi bỏ phiếu**, target B, Auto.
2. PID B bị terminate thật, HTTP PREPARE thất bại, phiếu B = MISSING.
3. Coordinator ghi ABORT, A/C áp dụng; B chưa ACK → DECISION_PENDING.
4. Nhấn **Khởi động & phục hồi**: B có PID mới, nhận cùng ABORT; tất cả cùng ABORT, run COMPLETED.

### D. Coordinator chết sau PREPARE — tình huống chính

1. Chọn **Coordinator chết sau PREPARE**, Auto (hoặc bước qua ba PREPARE rồi bước crash).
2. Sau VOTE YES của A/B/C, Coordinator gọi `os._exit(86)` **trước durable decision**.
3. UI vẫn cập nhật vì Supervisor còn sống. Coordinator đỏ, cả ba participant **PREPARED** màu vàng, bộ đếm = 0, transaction state PREPARING, run BLOCKED.
4. **Dừng trình bày 10–20 giây để cả lớp thấy không có timer tự ABORT.** PREPARED không đổi.
5. Nhấn từng node, chỉ ra durable transaction state và PID vẫn sống.
6. Nhấn **Khởi động & phục hồi**. Coordinator PID mới đọc đủ ba YES đã lưu; ghi COMMIT bền vững và phân phối. Các node COMMIT, counter 10.

Điểm lý thuyết: PREPARED participant không biết liệu COMMIT đã được ghi hoặc gửi nơi khác. Tự ABORT vì timeout có thể phá atomicity. Phục hồi ở đây do **Coordinator có thẩm quyền** đọc nhật ký bền vững; không phải participant tự thoát blocking bằng timeout.

## 8.6 — Recovery

### A–B. State và checkpoint

1. **Recovery → Ghi trạng thái bền vững**: hai operation `+5,+5`, state = **10**, journal có 2 operation.
2. **Tạo checkpoint**: snapshot `(value=10, seq=2)`. Nhấn Node A xem `checkpoint` và `operations`.

### C–E. Operation sau checkpoint, crash, restart và replay

1. Chọn **Crash → checkpoint + redo**, Từng bước, Chạy thí nghiệm.
2. Hai bước đầu: +5, +5 → 10.
3. Bước 3: checkpoint tại value 10, seq 2.
4. Bước 4–5: +7, +3 → **20**, checkpoint vẫn 10.
5. Bước 6: crash Node A. Node đỏ, không có counter live; file SQLite vẫn còn.
6. Bước 7: restart. PID đổi; boot report: checkpoint 10, replay 2 operations sau seq 2 → **20**.
7. So sánh `before`, `after`, `before_pid`, `after_pid` trong kết quả.

### F. Idempotence

1. Chọn **Phát lại nhiều lần**, Auto.
2. Sau recovery, gọi recover một lần nữa, rồi gửi lại operation ID số 4.
3. State vẫn **20**, journal vẫn **4 operation**, duplicate=true. Event IDEMPOTENCE chứa cả hai bằng chứng.

Phương pháp: **checkpoint + local logical redo logging** trên stable storage. SQLite bảo vệ atomic write của operation và counter. Replay chạy từ snapshot, không cộng lại trên state hiện tại. Không phải distributed checkpoint đồng bộ, không phục hồi ổ đĩa đã mất và không message logging mọi gói mạng.

## Câu hỏi giảng viên có thể hỏi

| Câu hỏi | Trả lời dựa trên implementation |
|---|---|
| Node có thực sự riêng process? | Có. So sánh PID/port trong inspector hoặc `/api/health`; mỗi child là Uvicorn riêng, state SQLite riêng. |
| Mất request/response là mất packet OS? | Không. Lỗi xác định ở wrapper transport ứng dụng. Request drop trước HTTP; response drop sau node đã thực thi. |
| Retry có exactly-once không? | Không. ID/result bền vững + atomic mutation cung cấp at-most-once trong phạm vi lưu ID. Client vẫn có thể không biết kết quả. |
| Dedup result và cập nhật bị crash ở giữa thì sao? | Chúng nằm trong cùng SQLite transaction; cả hai cùng commit hoặc cùng rollback, theo giả định durable SQLite. |
| ACK mất thì có duplicate delivery không? | Retry cùng message ID bị UNIQUE receipt chặn. Thí nghiệm duplicate minh họa cơ chế này; không có kịch bản riêng mất ACK multicast. |
| Đây có phải atomic multicast? | Không; không consensus, total order hoặc all-or-none delivery agreement. |
| 2PC có non-blocking không? | Không. Kịch bản Coordinator crash giữ PREPARED tới khi Coordinator phục hồi. |
| Participant NO có thể ABORT ngay không? | Có: nó chưa hứa COMMIT, ghi local NO/ABORT; Coordinator sau đó quyết định global ABORT. |
| Coordinator thiếu một vote có thể abort không? | Có, nếu chưa có durable COMMIT. Participant đã PREPARED phải đợi quyết định của Coordinator. |
| Crash sau durable COMMIT nhưng chưa gửi hết? | `/resolve` đọc cùng COMMIT và gửi lại; participant áp dụng idempotent. Không thay bằng ABORT. |
| Process restart khác reset thế nào? | Restart giữ DB và phục hồi; reset xóa state quản trị để tạo lab mới. |
| Replay lặp tại sao không tăng gấp đôi? | Dựng lại từ snapshot + suffix log; operation ID UNIQUE ngăn ghi lặp khi client gửi lại. |
| GUI có tự suy luận node đã commit không? | Không. State qua HTTP; sequence/timeline từ journal. Snapshot có độ trễ poll, không atomic toàn hệ thống. |
| Có chịu Byzantine/network partition thật không? | Không. Mô hình crash/unavailable + transport faults xác định, không triển khai Byzantine consensus hay OS partition. |
| Nếu Supervisor chết? | Đây là control plane ngoài protocol; không có HA cho Supervisor. Dừng sạch bằng Ctrl+C để thu hồi child processes. |

## Kết thúc

Xuất snapshot nếu cần. Reset là tùy chọn. Nhấn Ctrl+C ở terminal Supervisor để dừng lab; state trên ổ đĩa giữ nguyên cho lần khởi động sau, trừ khi đã reset.


## Điều khiển Control Center v2

N chạy bước tiếp khi backend WAITING. P tạm dừng/tiếp tục auto; chế độ từng bước dùng N. Nút Trình chiếu mở bố cục lớn, Esc thoát hoặc đóng inspector. Tạm dừng chỉ có hiệu lực tại ranh giới hành động để không ngắt giữa thao tác ghi.

Tốc độ thực thi (0.5× / 1× / 4×) điều chỉnh khoảng nghỉ giữa các hành động. Độ trễ transport là một cấu hình lỗi độc lập. Thông điệp chỉ sáng khi có sự kiện thực từ journal. Khi mất SSE, kết nối được đánh dấu mất; counter không được dựng giả.

Trong 2PC, quan sát PREPARE → DECISION → ACK và ba trạng thái participant. Khi Coordinator crash, cả ba PREPARED giữ khóa; banner BLOCKED giải thích vì sao không được tự ABORT. Chọn Khởi động & phục hồi để resolve.

Trong Recovery, đọc CHECKPOINT, TRƯỚC CRASH, STATE HIỆN TẠI và các dòng “Đã replay” trong durable operation log. Màu replay dựa trên report do node trả về.

SVG dự phòng vẫn dùng cùng API, cùng scenario và dữ liệu. Chuyển renderer không chạy lại hay phát lại giao thức. Có thể thử `/commit?renderer=svg` trước buổi trình bày.
