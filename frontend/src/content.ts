import { ArrowLeftRight, Users, GitBranch, History } from 'lucide-react'
import type { Module } from './types'

export const modules = {
  rpc: { section: '8.3', title: 'Reliable Client–Server', heading: 'Giao tiếp Client–Server', icon: ArrowLeftRight, accent: 'violet',
    subtitle: 'Khi một lời gọi không nhận được phản hồi, điều gì thực sự đã xảy ra?',
    short: 'Timeout, thử lại và ngữ nghĩa thực thi.',
    theory: 'Client không phân biệt được yêu cầu bị mất, server chết hay phản hồi bị mất chỉ qua timeout. Thử lại có thể làm một thao tác chạy nhiều lần. Request ID và bộ nhớ kết quả bền vững giúp thực thi at-most-once trong phạm vi lưu giữ ID.',
    limit: 'At-least-once chỉ đạt được khi cuối cùng giao được yêu cầu; số lần thử ở đây là hữu hạn. At-most-once có thể thực thi 0 lần. Không bảo đảm exactly-once trong hệ thống tổng quát.',
    tags: ['RPC qua HTTP', 'Timeout hữu hạn', 'Durable deduplication'] },
  group: { section: '8.4', title: 'Reliable Group Communication', heading: 'Giao tiếp nhóm tin cậy', icon: Users, accent: 'blue',
    subtitle: 'Một thông điệp. Ba thành viên. Không phải đường truyền nào cũng đáng tin.',
    short: 'Multicast, ACK và truyền lại chọn lọc.',
    theory: 'Sender gửi cùng message ID tới từng thành viên qua HTTP, thu ACK và truyền lại tới những node chưa xác nhận. Mỗi node lưu ID bền vững để giao cho ứng dụng tối đa một lần, dù thông điệp được truyền nhiều lần.',
    limit: 'Đây là reliable multicast theo ACK và truyền lại hữu hạn, chưa phải atomic multicast. Không bảo đảm thứ tự tổng, membership thay đổi hay tất cả cùng giao; node không khả dụng có thể chưa nhận khi kết thúc.',
    tags: ['ACK theo thành viên', 'Selective retransmission', 'Không phải atomic multicast'] },
  commit: { section: '8.5', title: 'Distributed Commit', heading: 'Cam kết phân tán', icon: GitBranch, accent: 'amber',
    subtitle: 'Ba cơ sở dữ liệu cần đưa ra cùng một quyết định: tất cả hoặc không.',
    short: 'Two-Phase Commit và giới hạn blocking.',
    theory: 'Pha 1: participant ghi PREPARED bền vững trước phiếu YES. Pha 2: Coordinator ghi COMMIT nếu mọi phiếu đều YES, ngược lại ABORT, rồi phân phối quyết định. Mỗi participant ghi và áp dụng quyết định trong một giao dịch SQLite.',
    limit: 'Một participant PREPARED không được tự ABORT vì timeout. Khi Coordinator chết, 2PC có thể blocking. Coordinator khởi động lại dùng quyết định hoặc phiếu đã ghi bền vững để tiếp tục; participant không tự đoán.',
    tags: ['2PC thực', 'Durable decision log', 'Blocking khi Coordinator chết'] },
  recovery: { section: '8.6', title: 'Recovery', heading: 'Phục hồi sau sự cố', icon: History, accent: 'green',
    subtitle: 'Tiến trình có thể mất. Những gì đã ghi bền vững thì còn lại.',
    short: 'Checkpoint, logical redo log và phục hồi.',
    theory: 'Node A duy trì bộ đếm và logical operation log trong SQLite. Checkpoint lưu (value, last sequence) nguyên tử. Khi tiến trình khởi động lại, node dựng lại giá trị từ snapshot rồi replay các operation có sequence lớn hơn checkpoint.',
    limit: 'Phục hồi cục bộ với logical redo logging; không phải coordinated distributed checkpoint hay phục hồi ổ đĩa hỏng. Replay bắt đầu lại từ snapshot; UNIQUE operation ID chống ghi và áp dụng lặp.',
    tags: ['Checkpoint + redo', 'Crash tiến trình thật', 'Replay idempotent'] },
} satisfies Record<Module, unknown>
