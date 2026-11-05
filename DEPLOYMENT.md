# Triển khai Fault Tolerance Lab

Đây là ứng dụng web có frontend React và **năm tiến trình Python** trên một máy. Bản build tĩnh không thể tự chạy Coordinator, các node, crash/restart hoặc SQLite. Chưa có cloud deployment nào được thực hiện trong phiên nâng cấp này.

## Local và Windows

```powershell
.\setup.bat
.\start.bat
# Hoặc Python hệ thống đã có dependency và bundle đã build:
.\start.bat -SystemPython
```

Mở http://127.0.0.1:8000. Các script Windows được giữ tương thích. Không dùng Uvicorn reload hoặc nhiều worker. Một supervisor quản lý một phiên demo chung.

Frontend development:

```powershell
# Terminal 1, thư mục gốc:
python -m backend
# Terminal 2:
cd frontend
npm ci
npm run dev
```

Vite tại http://127.0.0.1:5173 proxy /api tới LAB_API_URL. Production: `npm run build`, sau đó `python -m backend` phục vụ frontend/dist. Bundle có React Flow lẫn SVG fallback; nút renderer cho phép chuyển trực tiếp. `npm run build:offline` vẫn hỗ trợ build chỉ dùng SVG.

## URL và môi trường

Frontend đọc VITE_API_URL (mặc định /api), VITE_SSE_URL (mặc định API + /events). Đây là giá trị public được đóng vào bundle lúc build; không đưa password, OIDC secret hoặc gateway token vào VITE_*. Fetch/EventSource gửi cookie credentials để dùng gateway có HttpOnly session. WebSocket không cần thiết: dữ liệu trực tiếp dùng SSE.

Backend đọc LAB_PORT, LAB_DATA, LAB_PACE, LAB_TIMEOUT như trước. Biến bổ sung:

| Biến | Hành vi |
|---|---|
| LAB_PUBLIC=true | Bắt buộc gateway token >=32 ký tự; bảo vệ UI/API/docs |
| LAB_GATEWAY_TOKEN | Secret chỉ có ở backend và reverse proxy |
| LAB_INTERNAL_TOKEN | Token callback nội bộ; tự sinh nếu không cấu hình |
| LAB_ALLOWED_ORIGINS | Danh sách origin cụ thể, cách nhau bằng dấu phẩy; không cho * |
| LAB_ALLOW_PROCESS_CONTROL | false mặc định trong public mode; true chỉ cho instance giảng viên |

Python không tự đọc .env. Dùng biến shell hoặc systemd EnvironmentFile. Xem .env.example và frontend/.env.example.

Cross-origin: gateway của frontend/backend phải xác thực cùng người dùng và cho phép cookie theo chính sách domain thực tế. Khai báo chính xác origin ở backend; không dùng wildcard. Khuyến nghị production cùng origin để tránh third-party cookie restrictions. CORS không thay thế authentication. Mutation từ origin ngoài danh sách bị từ chối 403, kể cả khi đang chạy local.

## Kế hoạch production thực tế: một Linux VM

1. Cấp một VM có Python 3.11+, Node.js 20.19+ cho build, nginx có auth_request module và oauth2-proxy. Tạo user dịch vụ faultlab, source tại /opt/fault-lab; dữ liệu bền vững tại /var/lib/fault-lab. Không dùng filesystem tạm cho SQLite.
2. Tạo virtual environment, cài requirements.txt, chạy npm ci và npm run build. Giữ backend chỉ bind loopback. Không mở 8000, 8001, 8101–8103 hoặc 4180 ra Internet.
3. Tạo /etc/fault-lab/backend.env, chỉ owner dịch vụ/root đọc được. Đặt LAB_PUBLIC=true, LAB_DATA=/var/lib/fault-lab, LAB_GATEWAY_TOKEN là chuỗi ngẫu nhiên riêng cho instance. Ví dụ tạo token tại máy chủ: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Không commit token.
4. Cài deploy/fault-lab.service và kiểm tra đường dẫn/user. Unit dùng KillMode=control-group để dừng toàn bộ worker nếu supervisor bị dừng. Chỉ chạy một instance trên mỗi bộ port/data.
5. Đăng ký OIDC application với callback HTTPS. Cấu hình oauth2-proxy từ deploy/oauth2-proxy.cfg.example; cung cấp client/cookie secrets ở server và danh sách email được phép demo. Không cho tài khoản ngoài lớp/giảng viên.
6. Cài nginx template deploy/nginx.conf; thay domain, chứng chỉ TLS. Tạo gateway-headers.conf từ bản example với token khớp backend, chỉ root đọc được. Proxy ghi đè header từ trình duyệt; /internal/ luôn bị chặn.
7. Kiểm tra `nginx -t`, đăng nhập thật qua OIDC, kiểm tra role/allowlist và thử tài khoản bị từ chối trước khi mở 443. Không bật LAB_ALLOW_PROCESS_CONTROL cho instance public dùng chung. Scenario fault injection vẫn chỉ dành cho người dùng demo đã được xác thực.
8. Chạy smoke test RPC, 2PC BLOCKED → resolve và Recovery qua domain thật. Các bước TLS/OIDC/nginx trên VM chưa được chạy trong môi trường Windows này.

Người có quyền demo có thể tạo fault và reset phiên chung. Đây không phải dịch vụ multi-tenant hoặc sandbox cho người dùng Internet tùy ý. Nếu nhiều lớp/người dùng thao tác đồng thời, cấp VM/container riêng theo phiên với data/port riêng; không tăng Uvicorn workers trên cùng database. Không đưa user chưa tin cậy vào allowlist. Cần rà soát dependency Python hiện có trước triển khai Internet; phiên này giữ nguyên dependency backend để bảo toàn tương thích thuật toán.

## Health checks, SPA và SSE

- /healthz: liveness tối thiểu {status:ok}, không lộ PID.
- /readyz: 200 khi bốn worker còn sống, 503 khi có process dừng. **503 khi chèn crash có thể là kết quả demo đúng**; không cấu hình tự restart cả lab chỉ vì readyz degraded.
- /api/health: chi tiết tiến trình, được gateway bảo vệ trong public mode.
- /commit, /rpc, /group, /recovery: deep links có SPA fallback. Đường dẫn API/asset không tồn tại vẫn trả 404.
- Proxy SSE phải tắt buffering/cache và giữ read timeout đủ lớn. Snapshot khoảng 450 ms; UI đánh dấu mất kết nối nếu quá 10 giây không có dữ liệu.
- Không cache API hoặc SSE. Bảo vệ log và SQLite, backup khi lab ngừng ghi.

## Giới hạn và điều kiện trước public launch

Các cấu hình trên được chuẩn bị, chưa cài vào máy chủ công khai. Cần domain, chứng chỉ, thông tin OIDC và phê duyệt tài khoản cloud riêng. Gateway auth và các chốt bảo vệ backend được kiểm thử cục bộ; chưa xác minh tích hợp nhà cung cấp danh tính hoặc reverse proxy thật. Đây là một phòng lab cho người dùng được phép, không phải hệ thống phục vụ workload sản xuất hay HA.

Tài liệu tham khảo: [nginx auth_request](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html), [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/), [Vite environment variables](https://vite.dev/guide/env-and-mode), [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/).
