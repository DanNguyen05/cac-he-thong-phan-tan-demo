import os

BASE = int(os.environ.get("LAB_PORT", "8000"))
HOST = "127.0.0.1"
MANAGER_URL = f"http://{HOST}:{BASE}"
COORDINATOR_URL = f"http://{HOST}:{BASE + 1}"
NODES = {name: f"http://{HOST}:{BASE + 101 + i}" for i, name in enumerate("ABC")}
PACE = float(os.environ.get("LAB_PACE", "0.3"))
TIMEOUT = float(os.environ.get("LAB_TIMEOUT", "0.65"))

SCENARIOS = {
    "rpc": [
        ("normal", "Giao tiếp bình thường", "Yêu cầu và phản hồi được chuyển thành công."),
        ("lost_request", "Mất yêu cầu", "Yêu cầu đầu bị mất; client chờ timeout rồi thử lại."),
        ("lost_response", "Mất phản hồi", "Server đã thực thi, nhưng client không nhận được kết quả."),
        ("server_down", "Server không khả dụng", "Node A trả 503; client dừng sau số lần thử hữu hạn."),
        ("duplicate", "Nhân đôi thông điệp", "Transport gửi cùng request ID hai lần qua HTTP."),
        ("delay", "Phản hồi chậm", "Độ trễ ở transport vượt timeout; lần đầu không tới node."),
    ],
    "group": [
        ("normal", "Tất cả nhận thành công", "Sender thu ACK từ ba thành viên."),
        ("lost_message", "Mất thông điệp tại một node", "Chỉ gửi lại tới thành viên chưa ACK."),
        ("duplicate", "Gửi lặp thông điệp", "Khử trùng lặp bền vững theo message ID."),
        ("node_down", "Một thành viên không khả dụng", "Kết quả chỉ rõ thành viên chưa xác nhận."),
    ],
    "commit": [
        ("normal", "Tất cả bỏ phiếu YES", "Ghi COMMIT bền vững trước khi gửi quyết định."),
        ("vote_no", "Một thành viên bỏ phiếu NO", "Điều phối viên quyết định ABORT."),
        ("participant_crash", "Participant chết trước khi bỏ phiếu", "Dừng tiến trình thật; thiếu phiếu dẫn tới ABORT."),
        ("coordinator_crash", "Coordinator chết sau PREPARE", "Các node giữ PREPARED và chờ quyết định hợp lệ."),
    ],
    "recovery": [
        ("normal", "Ghi trạng thái bền vững", "Các phép cộng được ghi vào nhật ký trước khi trả lời."),
        ("checkpoint", "Tạo checkpoint", "Lưu snapshot cùng số thứ tự cuối cùng."),
        ("crash_recover", "Crash → checkpoint + redo", "Dừng node thật, khởi động lại và phát lại nhật ký."),
        ("idempotent", "Phát lại nhiều lần", "Khôi phục từ snapshot và dùng ID chống áp dụng lặp."),
    ],
}
