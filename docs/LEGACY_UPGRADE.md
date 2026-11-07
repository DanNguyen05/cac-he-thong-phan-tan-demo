# Redesign theo ảnh tham chiếu — Fault Tolerance Lab

Lần cập nhật này dùng ảnh thiết kế người dùng đính kèm làm nguồn bố cục chính. Đã đọc UI UX Pro Max và chạy workflow design-system/search; quyết định thiết kế được ghi ở [MASTER.md](design-system/fault-tolerance-lab/MASTER.md). Không cần Figma MCP.

## Giao diện đã triển khai

- Ba vùng desktop: sidebar gọn, workspace trung tâm, bảng điều khiển phải.
- Tiêu đề 36–40px, bốn chỉ số lớn, sơ đồ chiếm phần chính, timeline tối đa ba sự kiện thực.
- Panel chính chỉ giữ kịch bản, chạy, từng bước, đặt lại, tốc độ, fault mode và trạng thái.
- Chạy tự động chuyển thành Tạm dừng/Tiếp tục khi phù hợp. Chọn Từng bước trước khi Chạy để dùng nút Bước tiếp hoặc phím N.
- Cài đặt nâng cao, dedup/retry, node gây lỗi, độ trễ, nguyên lý và export nằm trong Cài đặt. Xem tất cả mở journal đầy đủ; nút thông tin ở sơ đồ 2PC mở sequence.
- React Flow và SVG cùng ngôn ngữ hình ảnh sáng, custom nodes và đường thông điệp có hướng; giữ zoom, pan, drag và inspector.
- 8.3 có hai đường request/response; 8.4 có ba recipient; 8.5 có Coordinator/participants và PREPARED/BLOCKED; 8.6 có checkpoint/redo log và kết quả replay.
- Presentation Mode, phím N/P/Esc, modal focus và reduced motion được giữ. Các màn hình thích ứng 375/768/1024/1440/1920px.

## Tệp thay đổi trong lần redesign

| Phạm vi | Tệp |
|---|---|
| Layout và tương tác UI | frontend/src/App.tsx, frontend/src/style.css |
| Tách orchestration hiện có khỏi view | frontend/src/useLab.ts |
| Metrics và timeline ngắn | frontend/src/LabSummary.tsx |
| Visualization | frontend/src/Diagram.tsx, frontend/src/ReactFlowDiagram.tsx, frontend/src/OfflineDiagram.tsx, frontend/src/topology.ts |
| Browser regression | frontend/e2e/lab.spec.ts, premium.spec.ts, theme.spec.ts, reference.spec.ts |
| Design system và hướng dẫn | design-system/fault-tolerance-lab/MASTER.md, README.md, DEMO_GUIDE.md, UPGRADE.md, VERIFICATION.md |
| Bundle và release | frontend/dist, release/fault-tolerance-lab.zip |

Toàn bộ 9 tệp Python backend được so sánh byte với bản trước khi sửa và không thay đổi. API, SSE, protocol algorithms, persistence, fault injection và Windows launcher giữ nguyên. Không migration database. useLab chỉ tách logic điều khiển frontend hiện có để layout dễ bảo trì.

## Khởi động

```powershell
.\start.bat -SystemPython
```

Mở http://127.0.0.1:8000/rpc. Nếu backend đã chạy, tải lại trang để nhận bundle mới, không cần reset dữ liệu. Máy mới chạy setup.bat trước; ZIP kèm bundle nên có thể setup.bat -SkipFrontend.

Phát triển: Python backend và npm run dev trong frontend ở hai terminal. Build: npm run build. SVG-only: npm run build:offline; chạy npm run build lại để trở về bundle React Flow chuẩn.

## Kiểm chứng và giới hạn

Kết quả thực thi ghi tại [VERIFICATION.md](VERIFICATION.md). Các test UI có reset/crash/restart nên dùng instance thử nghiệm riêng.

Ứng dụng chạy local như web thông thường. Cấu hình triển khai hiện có trong [DEPLOYMENT.md](DEPLOYMENT.md) được giữ; chưa deploy Internet. Public deployment vẫn cần TLS, authenticated gateway/OIDC, demo allowlist và các worker trên private/loopback. Một supervisor là một phiên demo chung. Pause dừng ở ranh giới hành động, không ngắt giữa lần gửi hoặc ghi. Presentation Mode không tự bật fullscreen hệ điều hành; dùng F11 khi cần.
