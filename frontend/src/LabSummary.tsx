import { Check, CheckCircle2, Clock, Database, List, RefreshCw, Send, Server, X } from 'lucide-react'
import type { LogEvent, Page, Snapshot } from './types'
import { tone } from './types'

type Metric = { label: string; value: string | number; color: string; icon: typeof Send }
export function LabMetrics({ page, state, connected }: { page: Page; state: Snapshot; connected: boolean }) {
  const events = state.events
  const tx = state.transactions[0]
  let metrics: Metric[]
  const count = (kind: string) => events.filter(event => event.kind === kind).length
  if (page === 'rpc') metrics = [
    { label: 'Yêu cầu', value: events.filter(e => e.kind === 'SEND' && e.data.path === '/rpc').length, color: 'blue', icon: Send },
    { label: 'Thành công', value: events.filter(e => e.kind === 'ACK' && e.data.path === '/rpc').length, color: 'green', icon: Check },
    { label: 'Retry', value: count('RETRY'), color: 'amber', icon: RefreshCw },
    { label: 'Lỗi', value: events.filter(e => ['TIMEOUT', 'UNAVAILABLE', 'ERROR'].includes(e.kind)).length, color: 'red', icon: X },
  ]
  else if (page === 'group') metrics = [
    { label: 'Đã gửi', value: events.filter(e => e.kind === 'SEND').length, color: 'blue', icon: Send },
    { label: 'Đã nhận', value: Object.values(state.nodes).filter(n => n.multicast?.length).length, color: 'green', icon: Check },
    { label: 'Truyền lại', value: count('RETRANSMIT'), color: 'amber', icon: RefreshCw },
    { label: 'Chưa nhận', value: state.run ? 3 - Object.values(state.nodes).filter(n => n.multicast?.length).length : 0, color: 'red', icon: X },
  ]
  else if (page === 'commit') metrics = [
    { label: 'Phiếu YES', value: Object.values(tx?.votes || {}).filter(v => v === 'YES').length, color: 'blue', icon: Check },
    { label: 'Xác nhận', value: Object.keys(tx?.acknowledgments || {}).length, color: 'green', icon: CheckCircle2 },
    { label: 'Quyết định', value: tx && ['COMMIT', 'ABORT'].includes(tx.state) ? tx.state : '—', color: tx?.state === 'ABORT' ? 'red' : 'blue', icon: Database },
    { label: 'PREPARED', value: Object.values(state.nodes).filter(n => n.transactions?.[0]?.state === 'PREPARED').length, color: 'amber', icon: Clock },
  ]
  else if (page === 'recovery') metrics = [
    { label: 'State hiện tại', value: state.nodes.A?.memory_value ?? '—', color: 'blue', icon: Server },
    { label: 'Checkpoint', value: state.nodes.A?.checkpoint?.value ?? '—', color: 'green', icon: Database },
    { label: 'Đã replay', value: state.nodes.A?.recovery?.replayed?.length ?? '—', color: 'amber', icon: RefreshCw },
    { label: 'Sau phục hồi', value: String(state.run?.result?.after ?? '—'), color: 'blue', icon: Check },
  ]
  else metrics = [
    { label: 'Tiến trình', value: Object.values(state.services).filter(s => s.alive).length + 1, color: 'blue', icon: Server },
    { label: 'Sự kiện', value: events.length, color: 'green', icon: List },
    { label: 'Sự cố', value: events.filter(e => /LOST|TIMEOUT|CRASH|ERROR/.test(e.kind)).length, color: 'amber', icon: RefreshCw },
    { label: 'SQLite', value: 4, color: 'blue', icon: Database },
  ]
  return <div className="stats-grid" aria-label="Số liệu trực tiếp">{metrics.map(({ label, value, color, icon: Icon }) =>
    <div className="stat-card" key={label}><span className={`stat-icon ${color}`}><Icon size={28} aria-hidden="true" /></span><div><span>{label}</span><strong data-testid={`metric-${label}`}>{connected ? value : '—'}</strong></div></div>
  )}</div>
}

export function keyEvents(events: LogEvent[]) {
  const major = events.filter(event => ['SEND', 'DELIVERED', 'ACK', 'RETRY', 'RETRANSMIT', 'TIMEOUT', 'UNAVAILABLE', 'REQUEST_LOST', 'RESPONSE_LOST', 'VOTE', 'DURABLE_DECISION', 'PROCESS_CRASH', 'RECOVERY', 'COORDINATOR_RECOVERY', 'CHECKPOINT', 'IDEMPOTENCE'].includes(event.kind))
  const last = major.slice(-3)
  const fault = [...major].reverse().find(event => /LOST|TIMEOUT|CRASH|UNAVAILABLE/.test(event.kind))
  if (fault && !last.some(e => e.seq === fault.seq) && last.length === 3) last[0] = fault
  return last.sort((a, b) => a.seq - b.seq)
}
const shortNames: Record<string, string> = { SEND: 'Gửi yêu cầu', DELIVERED: 'Node xử lý', ACK: 'Nhận phản hồi', RETRY: 'Thử lại', RETRANSMIT: 'Truyền lại', TIMEOUT: 'Hết thời gian chờ', UNAVAILABLE: 'Node không khả dụng', REQUEST_LOST: 'Mất yêu cầu', RESPONSE_LOST: 'Mất phản hồi', VOTE: 'Bỏ phiếu', DURABLE_DECISION: 'Ghi quyết định', PROCESS_CRASH: 'Tiến trình đã dừng', RECOVERY: 'Khôi phục state', COORDINATOR_RECOVERY: 'Phục hồi Coordinator', CHECKPOINT: 'Lưu checkpoint', IDEMPOTENCE: 'Bỏ qua bản trùng' }
export function CompactTimeline({ events, onSelect, onOpen }: { events: LogEvent[]; onSelect: (event: LogEvent) => void; onOpen: () => void }) {
  const entries = keyEvents(events)
  return <section className="panel compact-timeline" aria-label="Dòng sự kiện chính">
    <div className="section-heading"><h2><List size={23} />Dòng sự kiện</h2><button className="text-button" onClick={onOpen}>Xem tất cả</button></div>
    {entries.length ? <div className="timeline-steps">{entries.map(event => <button key={event.seq} className="timeline-step" onClick={() => onSelect(event)} title={event.detail}>
      <span className={`timeline-symbol ${tone(event.kind)}`}>{/LOST|TIMEOUT|CRASH|UNAVAILABLE/.test(event.kind) ? <X size={23} /> : event.kind === 'DELIVERED' ? <Server size={23} /> : /RETRY|RECOVERY|RETRANSMIT/.test(event.kind) ? <RefreshCw size={23} /> : <Check size={23} />}</span>
      <span><time>{new Date(event.time * 1000).toLocaleTimeString('vi-VN', { hour12: false })}</time><strong>{event.kind === 'VOTE' ? `VOTE ${event.data.vote}` : event.kind === 'DURABLE_DECISION' ? String(event.data.decision) : shortNames[event.kind] || event.kind}</strong></span>
    </button>)}</div> : <div className="timeline-empty"><span className="empty-step">1<span>Chọn kịch bản</span></span><i /><span className="empty-step">2<span>Chạy thí nghiệm</span></span><i /><span className="empty-step">3<span>Quan sát kết quả</span></span></div>}
  </section>
}
