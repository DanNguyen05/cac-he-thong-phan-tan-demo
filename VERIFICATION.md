# Kiểm chứng redesign theo ảnh tham chiếu

Ngày 2026-11-05. Windows, Python 3.11.9, Node.js 20.20.2, Microsoft Edge qua Playwright 1.63. React 19.1, React Flow 12.12.1, TypeScript 6.0.3, Vite 6.4.5.

Đã phân tích ảnh tham chiếu trước khi sửa, tái cấu trúc layout và đối chiếu ảnh chụp ứng dụng chạy thật. Đã đọc UI UX Pro Max, chạy design-system generation và UX search. Quyết định thiết kế ở design-system/fault-tolerance-lab/MASTER.md. Không sử dụng hoặc suy đoán dữ liệu Figma.

## Kết quả thực chạy

| Hạng mục | Kết quả | Báo cáo |
|---|---|---|
| Backend | 32 passed, 0 lỗi, 39.934 giây | test-results/reference-backend.xml |
| Frontend trước vòng tinh chỉnh cuối | 16 passed, 0 failed/flaky/skipped | test-results/frontend-reference.json |
| Frontend production cuối | 18 passed, 0 failed/flaky/skipped | test-results/frontend-reference-final.json |
| SVG-only production cuối | 8 passed, 0 failed/flaky/skipped | test-results/frontend-reference-offline-final.json |
| TypeScript strict | npm run typecheck — pass | Chạy trước production build cuối |
| Production React Flow | npm run build — pass | Bundle dùng cho release |
| SVG-only build | npm run build:offline — pass | Đã chạy browser tests trên chính bundle SVG này |
| Responsive | 375 / 768 / 1024 / 1440 / 1920px | Cả năm workspace, không tràn ngang document |

Production cuối: JS khoảng 459.28 KB (gzip 145.23 KB), CSS 55.36 KB (gzip 11.55 KB). Bundle SVG-only khoảng 262.04 KB JS (gzip 80.69 KB). Sau kiểm thử offline đã build lại bundle React Flow tiêu chuẩn; SVG fallback vẫn có sẵn trong bundle chuẩn.

Toàn bộ 9 file Python backend được so sánh byte với test-results/reference-before.zip: không thay đổi. API, thuật toán, process management, persistence và fault injection giữ nguyên. Backend có một PendingDeprecationWarning hiện hữu từ starlette/python_multipart; không có lỗi test.

## Browser coverage

Các kiểm thử dùng HTTP/backend thật, không mock sự kiện hoặc kết quả:

- Tổng quan/process inspector/PID và cả bốn deep links.
- RPC normal, lost response, retry/dedup, tắt dedup tạo hai lần thực thi, raw event JSON.
- Multicast mất message tại B, retransmit chỉ recipient thiếu, delivery state, tìm kiếm journal.
- 2PC crash Coordinator thật, ba participant PREPARED, BLOCKED, sequence khớp journal, resolve về COMMIT.
- Recovery crash/restart với PID mới, checkpoint 10, replay hai operation, state sau recovery 20, operation log đánh dấu replay.
- Run/Step/Reset, fault switches chọn scenario thật và loại trừ nhau, tốc độ 2× thực sự gửi pace_ms=300.
- N/P/Esc sau click button; nhập N/P trong search không gây điều khiển protocol.
- React Flow zoom/drag/inspect, SVG runtime và SVG-only, native dialog focus containment/restoration, reduced motion.
- Light Mode cố định, các semantic text roles đạt contrast >=4.5:1 trên trắng và #F8FAFC.
- Panel chính chỉ có một scenario select, bốn metric thực khớp API, timeline tối đa ba sự kiện, current status nhìn thấy ngay trong desktop 1672×940.

## Đối chiếu trực quan

Đã mở xem ảnh RPC 1672px/1440px, Group, 2PC blocking và presentation, Recovery, SVG và mobile. Đã chỉnh các sai khác chính: số vùng bố cục, tỷ lệ sidebar/control panel, kích thước tiêu đề/node, màu ONLINE, đường request/response tách biệt, tách nhãn participant và tránh nhãn Recovery bị node che.

Ảnh minh chứng cục bộ:
- test-results/reference-final-rpc-1672.png
- test-results/reference-final-rpc-1440.png
- test-results/reference-final-group.png
- test-results/reference-final-recovery.png
- test-results/reference-2pc-blocked.png
- test-results/reference-2pc-presentation.png
- test-results/reference-svg.png
- test-results/reference-commit-{375,768,1024,1440,1920}.png

Artifact, database thử nghiệm và node_modules không đóng vào release. Giá trị trong ảnh là kết quả run thật, không cố tái tạo các số 24/22/2/0 minh họa của thiết kế.

## Chạy lại

Khởi động một instance lab riêng vì UI tests có Reset/crash/restart:

```powershell
$env:LAB_PORT='9900'
$env:LAB_DATA="$PWD\test-results\manual-ui"
python -m backend
```

Ở terminal khác:

```powershell
python -m pytest tests -q
cd frontend
npm run typecheck
npm run build
$env:LAB_UI_URL='http://127.0.0.1:9900'
npx playwright test

# SVG-only regression:
npm run build:offline
npx playwright test lab.spec.ts
# Trả về bundle chuẩn:
npm run build
```

Trong môi trường NVM Windows hiện tại đã dùng NODE_OPTIONS=--preserve-symlinks --preserve-symlinks-main. Kiểm thử dùng port 9900 và dữ liệu riêng, không reset hoặc restart phiên người dùng ở port 8000.

## Giới hạn và triển khai

Web local được kiểm tra HTTP 200, deep link /rpc và SSE trực tiếp tại port 8000. Trạng thái fault của phiên người dùng được giữ; frontend hiển thị đúng các node đang offline. Windows start.bat/scripts/start.ps1 không thay đổi.

Chưa triển khai cloud/Internet hoặc kiểm chứng TLS/OIDC/nginx trên máy chủ. Cấu hình hiện có ở DEPLOYMENT.md được giữ; public deployment cần authenticated gateway, demo allowlist và private worker ports. Một supervisor là một phiên demo dùng chung; không multi-tenant/HA. Static hosting không chạy thay các Python worker.

Pause có hiệu lực trước hành động kế tiếp; không ngắt HTTP/ghi đang thực hiện. Presentation Mode không tự bật fullscreen trình duyệt; dùng F11. Reliable multicast không có atomic/total-order agreement. Recovery là logical redo logging cục bộ.

Release được tạo bằng scripts/package.py; kiểm tra CRC, source và production bundle khớp workspace, loại trừ database, secrets và node_modules.
