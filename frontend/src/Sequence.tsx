import type { LogEvent } from './types'

export default function Sequence({ events, onSelect }: { events: LogEvent[]; onSelect: (event: LogEvent) => void }) {
  const rows = events.filter(e => (e.kind === 'SEND' && ['/prepare', '/decision'].includes(String(e.data.path))) || e.kind === 'VOTE' || e.kind === 'DURABLE_DECISION' || e.kind === 'PROCESS_CRASH' || e.kind === 'COORDINATOR_RECOVERY')
  const height = Math.max(220, 80 + rows.length * 36)
  const xs: Record<string, number> = { Coordinator: 100, A: 320, B: 520, C: 720, Disk: 100 }
  return <section className="panel sequence-panel"><div className="panel-heading"><h3>Sơ đồ trình tự <span className="muted">/ Two-Phase Commit</span></h3><span className="badge violet">Từ sự kiện thực</span></div>
    <div className="sequence-scroll"><svg viewBox={`0 0 820 ${height}`} role="img" aria-label="Sơ đồ trình tự 2PC từ thông điệp HTTP thực">
      <defs>{['blue', 'green', 'red', 'amber'].map((color, i) => <marker key={color} id={`arrow-${color}`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill={['var(--blue)', 'var(--green)', 'var(--red)', 'var(--amber)'][i]} /></marker>)}</defs>
      {['Coordinator', 'A', 'B', 'C'].map(name => <g key={name}><line x1={xs[name]} x2={xs[name]} y1={50} y2={height - 15} stroke="var(--border-strong)" strokeDasharray="4 5" /><rect x={xs[name] - 68} y={10} width={136} height={30} rx={6} fill="var(--surface-raised)" stroke="var(--border-strong)" /><text x={xs[name]} y={30} textAnchor="middle" fill="var(--text)" fontSize={12}>{name === 'Coordinator' ? name : `Participant ${name}`}</text></g>)}
      {rows.map((event, index) => {
        const y = 78 + index * 36
        const from = xs[event.source] ?? 100, to = xs[event.target] ?? 100
        const response = event.data.response as { state?: string } | undefined
        const text = event.kind === 'VOTE' ? `VOTE ${event.data.vote}` : event.kind === 'SEND' ? event.data.path === '/prepare' ? 'PREPARE' : response?.state || (events.find(e => e.kind === 'DURABLE_DECISION')?.data.decision as string) || 'DECISION' : event.kind === 'DURABLE_DECISION' ? `DISK: ${event.data.decision}` : event.kind === 'PROCESS_CRASH' ? 'CRASH · PREPARED BLOCKING' : 'RECOVER COORDINATOR'
        const color = text.includes('ABORT') || text.includes('CRASH') || text.includes('NO') ? 'red' : text.includes('COMMIT') || text.includes('YES') ? 'green' : event.kind === 'DURABLE_DECISION' ? 'amber' : 'blue'
        const stroke = { blue: 'var(--blue)', green: 'var(--green)', red: 'var(--red)', amber: 'var(--amber)' }[color]
        return <g className="sequence-event" key={event.seq} onClick={() => onSelect(event)} role="button" tabIndex={0} onKeyDown={e => e.key === 'Enter' && onSelect(event)} aria-label={`${text} sự kiện ${event.seq}`}><title>{event.detail}</title><rect x={10} y={y - 22} width={800} height={34} fill="transparent" />{from !== to ? <><line x1={from} x2={to} y1={y} y2={y} stroke={stroke} markerEnd={`url(#arrow-${color})`} /><text x={(from + to) / 2} y={y - 7} textAnchor="middle" fill={stroke} fontSize={12}>{text}</text></> : <><rect x={from - 60} y={y - 18} width={250} height={27} rx={5} fill="var(--bg)" stroke={stroke} /><text x={from - 50} y={y} fill={stroke} fontSize={12}>{text}</text></>}</g>
      })}
      {!rows.length && <text x={410} y={145} textAnchor="middle" fill="var(--muted)" fontSize={12}>Chạy kịch bản để theo dõi PREPARE → VOTE → COMMIT / ABORT</text>}
    </svg></div></section>
}
