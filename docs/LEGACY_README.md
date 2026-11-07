# Distributed Systems — Fault Tolerance Lab

Phòng thực hành tương tác bằng tiếng Việt cho chương 8, mục 8.3–8.6, *Distributed Systems*, 4th Edition, Maarten van Steen & Andrew S. Tanenbaum. Bốn giao thức chạy qua HTTP giữa các tiến trình Python độc lập; giao diện đọc sự kiện và trạng thái thật.

## Chạy trên Windows

Yêu cầu Python **3.11+**, Node.js **20.19+** và npm. Không cần Docker, tài khoản cloud hay API trả phí. Lần cài dependency đầu tiên cần Internet hoặc cache npm/pip đầy đủ.

```powershell
.\setup.bat
.\start.bat
```

Mở **http://127.0.0.1:8000**. `start.bat` chạy một Supervisor, một Coordinator và ba node; nhấn **Ctrl+C** trong terminal để dừng các tiến trình con. Khởi tạo database tự động. Không dùng `--reload` hoặc nhiều Uvicorn workers: lab cần một supervisor duy nhất.

Nếu dependency Python đã có trong môi trường hệ thống và `frontend/dist` đã được build:

```powershell
.\start.bat -SystemPython
```

### Cài đặt thủ công

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
.\.venv\Scripts\python.exe -m backend
```

Giao diện đã build được phục vụ từ FastAPI, không cần chạy Node khi trình bày. Để phát triển, chạy backend và `npm run dev` ở hai terminal; mở http://127.0.0.1:5173. Vite proxy `/api` tới port 8000.

### Giao diện theo ảnh tham chiếu

Giao diện Light Mode được tái cấu trúc theo ảnh thiết kế: sidebar gọn, bốn chỉ số lớn, topology ở trung tâm, bảng điều khiển phải và ba sự kiện chính phía dưới. Mở **http://127.0.0.1:8000/rpc**, chọn kịch bản, nhấn **Chạy thí nghiệm** và quan sát kết quả. Cùng design system áp dụng cho 8.4, 8.5 và 8.6 với sơ đồ riêng.

React Flow 12.12.1 có custom nodes/edges, zoom, pan, fit, drag và inspector. **SVG fallback** vẫn có trong bundle: mở **Cài đặt > Bộ hiển thị**, hoặc query `?renderer=svg`. Cấu hình retry/dedup/node/độ trễ và nguyên lý nằm trong Cài đặt; **Xem tất cả** mở journal đầy đủ. Nút thông tin của sơ đồ 2PC mở sequence.

[Design system](design-system/fault-tolerance-lab/MASTER.md) ghi cách áp dụng UI UX Pro Max và ảnh tham chiếu. Metrics, timeline, sequence và animation đều dựa trên API/SSE thật; không gán số liệu mẫu từ ảnh. Backend và Windows launcher không thay đổi trong lần redesign này.

```powershell
cd frontend
npm ci
npm run build
# TypeScript:
npm run typecheck
# Build chỉ dùng SVG nếu cần:
npm run build:offline
```

N/P/Esc hoạt động khi nút giữ focus và không chặn nhập văn bản. **N** chạy bước tiếp khi WAITING; **P** tạm dừng/tiếp tục auto tại ranh giới hành động; nút **Trình chiếu** mở bố cục lớp học; **Esc** đóng inspector hoặc thoát trình chiếu. Tốc độ thực thi thay đổi nhịp giữa hành động backend; độ trễ transport và timeout vẫn độc lập.

Bản `release/fault-tolerance-lab.zip` gồm source, bundle React Flow + SVG, lockfile, design system, mẫu môi trường và cấu hình triển khai. Không kèm database, token, node_modules hoặc cache. Sau giải nén dùng `setup.bat -SkipFrontend` rồi `start.bat`, hoặc `start.bat -SystemPython` nếu dependency Python đã có.

### Chạy như ứng dụng web

FastAPI phục vụ frontend production và hỗ trợ deep links /rpc, /group, /commit, /recovery. API/SSE URL và CORS có thể cấu hình. Xem [DEPLOYMENT.md](DEPLOYMENT.md) cho local development, reverse proxy SSE, health checks, authentication/OIDC, giới hạn admin và kế hoạch Linux VM. Python và các worker phải thực sự chạy; static hosting riêng không thay thế backend.

## Các thí nghiệm

| Mục | Thực thi | Tình huống xác định |
|---|---|---|
| 8.3 | RPC cộng bộ đếm tại Node A | Thành công, mất request, mất response, unavailable, delay, duplicate; bật/tắt retry và dedup |
| 8.4 | Reliable multicast fan-out tới A/B/C | ACK, mất tại node được chọn, retransmit, khử duplicate, thành viên lỗi |
| 8.5 | Two-Phase Commit | All YES → COMMIT; NO → ABORT; participant crash; Coordinator crash sau PREPARED → blocking; phục hồi quyết định |
| 8.6 | Checkpoint + logical redo logging | Ghi operation, checkpoint, crash thật, restart, replay, gửi operation trùng |

Chọn **Từng bước** trước khi nhấn **Chạy thí nghiệm**. Chế độ này dừng backend trước mỗi hành động giao thức; nút **Bước tiếp** / phím **N** mới thực thi hành động tiếp. **P** tạm dừng/tiếp tục chế độ tự động; dùng nút **Trình chiếu** để mở; **Esc** thoát. Nhấn node xem PID, database state và điều khiển crash/restart; nhấn sự kiện để xem JSON gốc. Xuất snapshot JSON để lưu minh chứng.

## Kiểm thử

```powershell
.\test.bat
# Để build và kiểm tra riêng SVG fallback:
.\test.bat -Offline
# Backend + build offline + UI (lab phải đang chạy):
.\test.bat -Offline -Browser
# Hoặc chỉ chạy backend:
python -m pytest tests -q
# UI end-to-end: khởi động lab trước, sau đó:
cd frontend
npx playwright test
```

Backend tests khởi động **năm tiến trình thật**, dùng HTTP loopback, database tạm và bộ port riêng; không mock node. Bao phủ các trường hợp RPC, multicast, 2PC, checkpoint/recovery, step mode, SSE, reset và chạy liên tiếp. UI tests dùng Chromium/Edge (`npx playwright install chromium` nếu chưa có browser), gọi backend đang chạy ở `LAB_UI_URL` (mặc định 8000). Xem [VERIFICATION.md](VERIFICATION.md) để biết kết quả thực chạy và giới hạn kiểm chứng.

## Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `LAB_PORT` | `8000` | Supervisor; Coordinator = +1, A/B/C = +101/+102/+103 |
| `LAB_DATA` | `./data` | Thư mục bốn database SQLite và process logs |
| `LAB_PACE` | `0.3` | Giây nghỉ giữa hành động ở auto mode; chỉ hỗ trợ quan sát |
| `LAB_TIMEOUT` | `0.65` | Deadline mỗi lần gửi, tính cả delay/drop của transport |
| `LAB_API_URL` | `http://127.0.0.1:8000` | Backend proxy của Vite khi phát triển |
| `LAB_UI_URL` | `http://127.0.0.1:8000` | URL trong bộ test giao diện |

```powershell
$env:LAB_PORT='8200'
$env:LAB_DATA="$PWD\data-session-2"
python -m backend
```

Tất cả service chỉ bind `127.0.0.1`. Local mode dành cho máy trình bày. Internet deployment phải bật LAB_PUBLIC và gateway được xác thực như DEPLOYMENT.md; không mở trực tiếp các port backend.

## Lưu ý vận hành

- **Reset xóa toàn bộ dữ liệu thí nghiệm**, kể cả PREPARED chưa có quyết định. Đây là reset quản trị, không phải recovery hay ABORT của giao thức.
- Khi 2PC blocking, dùng **Khởi động & phục hồi** để Coordinator đọc durable log rồi gửi quyết định. Không khởi chạy thí nghiệm mới trên một transaction chưa xử lý.
- Mỗi lần bắt đầu kịch bản mới sẽ làm mới trạng thái các node; run và event trước vẫn còn trong journal tới lần Reset. Đây là lab một người trình bày, một kịch bản tại một thời điểm.
- Nếu port bận: dừng lab cũ bằng Ctrl+C hoặc chọn `LAB_PORT` khác. Xem `data/process-logs/*.log` để chẩn đoán service không khởi động được.
- Nếu chỉ restart node, trạng thái bền vững vẫn còn. Nếu xóa file database thì không thể phục hồi state đó.

Chi tiết: [ARCHITECTURE.md](ARCHITECTURE.md), [DEMO_GUIDE.md](DEMO_GUIDE.md), [API.md](API.md).

Tài liệu thư viện: [React Flow](https://reactflow.dev/learn), [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/), [SQLite transactions](https://www.sqlite.org/lang_transaction.html).

## Light Mode thống nhất

Toàn bộ giao diện dùng Light Mode: nền #F8FAFC, card/node/modal trắng, chữ slate và primary #0669E8. Không có nút chuyển Dark Mode; lựa chọn tối đã lưu trước đây không được áp dụng. React Flow, SVG, timeline, code blocks và Presentation Mode dùng cùng semantic tokens. Backend/API/giao thức không thay đổi trong lần chỉnh giao diện này.
