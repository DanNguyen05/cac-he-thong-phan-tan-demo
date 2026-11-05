import { Check, Database, LockKeyhole, RotateCcw } from 'lucide-react'
import type { Module, Snapshot } from './types'
import { tone } from './types'

export default function ProtocolState({ page, state }: { page: Module; state: Snapshot }) {
  const tx = state.transactions[0]
  if (page === 'commit') {
    const blocked = state.run?.status === 'BLOCKED'
    const decided = tx && ['COMMIT', 'ABORT'].includes(tx.state)
    return <section className={`protocol-state ${blocked ? 'is-blocked' : ''}`} aria-label="Trạng thái giao thức 2PC">
      <div className="phase-rail"><span className={tx ? 'reached' : ''}><b>01</b> PREPARE <small>Thu phiếu bền vững</small></span><span className={decided ? 'reached' : blocked ? 'blocked-phase' : ''}><b>{blocked ? <LockKeyhole size={16} /> : '02'}</b> {blocked ? 'BLOCKED' : 'DECISION'} <small>{blocked ? 'Chờ Coordinator phục hồi' : 'Ghi COMMIT / ABORT'}</small></span><span className={state.run?.status === 'COMPLETED' ? 'reached' : ''}><b>03</b> ACK <small>Xác nhận từng participant</small></span></div>
      <div className="participant-strip">{['A', 'B', 'C'].map(name => {
        const node = state.nodes[name], transaction = node?.transactions?.[0]
        return <div key={name}><strong>Participant {name}</strong><span className={`badge ${tone(transaction?.state || '')}`}>{node?.crashed ? 'CRASHED' : transaction?.state || 'IDLE'}</span><small>VOTE <b>{tx?.votes[name] || '—'}</b> · ACK <b>{tx?.acknowledgments[name] ? '✓' : '—'}</b></small>{transaction?.state === 'PREPARED' && <small className="amber-text"><LockKeyhole size={12} /> Giữ khóa · không tự ABORT</small>}</div>
      })}</div>
    </section>
  }
  if (page === 'recovery') {
    const node = state.nodes.A
    const replayed = node?.recovery?.replayed || []
    const before = state.events.find(e => e.kind === 'BEFORE_CRASH')?.data.value
    return <section className="protocol-state recovery-state" aria-label="Checkpoint và nhật ký phục hồi"><div className="recovery-comparison">
      <div><Database size={18} /><small>CHECKPOINT</small><strong>{node?.checkpoint?.value ?? '—'}</strong><span>sequence #{node?.checkpoint?.seq ?? '—'}</span></div>
      <div><LockKeyhole size={18} /><small>TRƯỚC CRASH</small><strong>{String(before ?? '—')}</strong><span>State đọc từ node</span></div>
      <div><RotateCcw size={18} /><small>STATE HIỆN TẠI</small><strong>{node?.memory_value ?? '—'}</strong><span>{node?.crashed ? 'Tiến trình đã dừng' : `${replayed.length} operations replayed`}</span></div>
    </div><div className="operation-log"><span className="field-label">DURABLE OPERATION LOG</span>{node?.operations?.length ? node.operations.map(op => <div className={replayed.includes(op.id) ? 'replayed' : ''} key={op.id}><code>#{op.seq}</code><span>{op.id.slice(-12)}</span><strong>{op.delta >= 0 ? '+' : ''}{op.delta}</strong><span>{replayed.includes(op.id) ? <><Check size={14} /> Đã replay</> : op.seq <= (node.checkpoint?.seq || 0) ? 'Trong checkpoint' : 'Sau checkpoint'}</span></div>) : <p className="muted">{node?.crashed ? 'Nhật ký còn trên ổ đĩa; restart để đọc lại.' : 'Chạy kịch bản để ghi operation và tạo checkpoint.'}</p>}</div></section>
  }
  return null
}
