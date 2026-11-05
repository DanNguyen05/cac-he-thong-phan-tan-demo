import { useState } from 'react'
import { Activity, List, Search, ArrowUpRight, Radio, Database } from 'lucide-react'
import type { LogEvent, Snapshot } from './types'
import { tone } from './types'

export default function EventLog({ state, selected, onSelect }: { state: Snapshot; selected: number | null; onSelect: (event: LogEvent) => void }) {
  const [tab, setTab] = useState('timeline')
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState(120)
  const [onlyFaults, setOnlyFaults] = useState(false)
  const filtered = state.events.filter(e => (!search || `${e.kind} ${e.source} ${e.target} ${e.detail} ${JSON.stringify(e.data)}`.toLowerCase().includes(search.toLowerCase())) && (!onlyFaults || /LOST|TIMEOUT|CRASH|ERROR|RETRY|UNAVAILABLE|ABORT/.test(e.kind)))
  const messages = filtered.filter(e => e.data.message_id || e.kind === 'VOTE' || e.kind === 'DURABLE_DECISION')
  return <section className="panel event-panel">
    <div className="panel-heading event-heading"><div className="log-tabs" role="tablist" aria-label="Dạng nhật ký">
      <button role="tab" aria-selected={tab === 'timeline'} aria-controls="event-log-content" className={tab === 'timeline' ? 'active' : ''} onClick={() => setTab('timeline')}><Activity size={15} /> Timeline</button>
      <button role="tab" aria-selected={tab === 'messages'} aria-controls="event-log-content" className={tab === 'messages' ? 'active' : ''} onClick={() => setTab('messages')}><List size={15} /> Thông điệp <small>{messages.length}</small></button>
      <button role="tab" aria-selected={tab === 'nodes'} aria-controls="event-log-content" className={tab === 'nodes' ? 'active' : ''} onClick={() => setTab('nodes')}><Database size={15} /> Nhật ký node</button>
    </div><span className="muted mono">{state.events.length} events</span></div>
    <div className="log-tools"><label className="search"><Search size={14} /><input aria-label="Tìm kiếm sự kiện" placeholder="Tìm sự kiện, message ID, node..." value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label className="check-label"><input type="checkbox" checked={onlyFaults} onChange={e => setOnlyFaults(e.target.checked)} /> Chỉ lỗi & thử lại</label></div>
    <div className="log-body" id="event-log-content" role="tabpanel" aria-label="Nội dung nhật ký">
      {tab === 'nodes' ? <div className="node-log-grid">{Object.entries(state.nodes).map(([name, node]) => <div key={name}><h4>Node {name} <span className="muted">SQLite log</span></h4>
        {node.crashed ? <p className="red-text">Tiến trình đã dừng. Nhật ký còn trên ổ đĩa.</p> : node.logs?.length ? node.logs.filter(log => !search || JSON.stringify(log).toLowerCase().includes(search.toLowerCase())).map(log => <div className="node-log" key={log.seq}><span className="muted mono">#{log.seq}</span><strong className={`${tone(log.kind)}-text`}>{log.kind}</strong><code>{log.id}</code><small>{log.data}</small></div>) : <p className="muted">Chưa có operation.</p>}</div>)}</div>
      : !filtered.length ? <div className="empty-state"><Radio size={28} /><strong>{state.events.length ? 'Không tìm thấy sự kiện' : 'Đang chờ thí nghiệm đầu tiên'}</strong><p>{state.events.length ? 'Thử đổi bộ lọc hoặc từ khóa.' : 'Chọn kịch bản rồi bắt đầu. Sự kiện sẽ xuất hiện từ backend qua SSE.'}</p></div>
      : tab === 'timeline' ? <div className="timeline">{[...filtered].reverse().slice(0, limit).map(event => <button key={event.seq} className={`timeline-row ${selected === event.seq ? 'selected' : ''}`} onClick={() => onSelect(event)}>
        <span className={`timeline-dot ${tone(event.kind)}`} /><time>{new Date(event.time * 1000).toLocaleTimeString('vi-VN', { hour12: false })}</time>
        <span className={`event-kind ${tone(event.kind)}`}>{event.kind}</span><span className="timeline-content"><strong>{event.source}{event.target && <> <ArrowUpRight size={12} /> {event.target}</>}</strong><span>{event.detail}</span></span><span className="event-seq">#{event.seq}</span>
      </button>)}</div>
      : <div className="table-scroll"><table><thead><tr><th>SEQ</th><th>MESSAGE / OPERATION ID</th><th>ĐƯỜNG ĐI</th><th>LẦN</th><th>SỰ KIỆN</th></tr></thead><tbody>{[...messages].reverse().slice(0, limit).map(event => <tr key={event.seq} onClick={() => onSelect(event)} tabIndex={0} onKeyDown={e => e.key === 'Enter' && onSelect(event)}><td>#{event.seq}</td><td><code>{String(event.data.message_id || event.data.transaction_id || '—')}</code><small>{String(event.data.operation_id || event.data.path || '')}</small></td><td>{event.source} → {event.target || '—'}</td><td>{String(event.data.attempt || '—')}</td><td><span className={`badge ${tone(event.kind)}`}>{event.kind}</span></td></tr>)}</tbody></table></div>}
    </div>
    {filtered.length > limit && tab !== 'nodes' && <button className="button ghost load-events" onClick={() => setLimit(value => value + 120)}>Xem thêm sự kiện ({filtered.length - limit} còn lại)</button>}
    <div className="panel-footer"><span><span className="live-dot" /> Nhật ký bền vững · dữ liệu backend</span><span>Nhấn sự kiện để xem chi tiết</span></div>
  </section>
}
