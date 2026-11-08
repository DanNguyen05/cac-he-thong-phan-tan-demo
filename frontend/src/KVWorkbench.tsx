import { useEffect, useState } from 'react'
import { CheckCircle2, Database, Pause, Play, SkipForward } from 'lucide-react'
import { apiBase } from './api'
import type { Page, Snapshot } from './types'

export default function KVWorkbench({ state, page, onEdit, onCatchup }: { state: Snapshot; page: Page; onEdit: () => void; onCatchup: () => void }) {
  const result = state.run?.result
  const stage = String(result?.stage || result?.phase || '')
  const external = ['RUNNING', 'WAITING'].includes(state.run?.status || '') && ['PAUSED_AFTER_PREPARE', 'PAUSED_AFTER_COMMIT', 'AWAIT_CONTAINER_RESTART', 'AWAIT_RPC_STOP', 'AWAIT_RECEIVER_STOP'].includes(stage)
  const names = page === 'rpc' ? ['rpc'] : page === 'recovery' ? ['A'] : ['A', 'B', 'C']
  const target = String(state.run?.config.target || 'B')
  const participantCrash = state.run?.scenario === 'participant_prepared'
  const service = stage === 'AWAIT_CONTAINER_RESTART' ? 'participant-a' : stage === 'AWAIT_RPC_STOP' ? 'rpc' : participantCrash || stage === 'AWAIT_RECEIVER_STOP' ? `participant-${target.toLowerCase()}` : 'coordinator'
  const command = `.\u005cscripts\u005ckv-demo.ps1 -Action ${stage === 'AWAIT_CONTAINER_RESTART' ? 'crash' : 'stop'} -Service ${service}`
  const missing = result?.missing_nodes
  const catchup = Array.isArray(missing) ? String(missing[0] || target) : target
  return <div className="kv-workbench" data-testid="kv-workbench">
    <div className="kv-heading"><h3><Database size={20} />Dữ liệu KV thực</h3><div><span className={`badge ${state.runtime?.containerized ? 'blue' : 'amber'}`}>{state.runtime?.containerized ? 'Docker' : 'Process · không phải Docker'}</span><button className="text-button" onClick={onEdit}>GET / PUT</button></div></div>
    {external && <div className="external-fault" role="status"><strong>{stage === 'PAUSED_AFTER_PREPARE' ? participantCrash ? `PREPARED · dừng Participant ${target}, rồi Bước tiếp` : 'PREPARED · chưa ghi quyết định' : stage === 'PAUSED_AFTER_COMMIT' ? 'COMMIT bền vững · B/C chưa nhận' : stage === 'AWAIT_CONTAINER_RESTART' ? 'Đang chờ crash và restart Node A thật' : stage === 'AWAIT_RECEIVER_STOP' ? `Đang chờ dừng receiver ${target} thật` : 'Đang chờ dừng RPC Server thật'}</strong>{state.runtime?.containerized ? <><code>{command}</code><code>{`.\u005cscripts\u005ckv-demo.ps1 -Action start -Service ${service}`}</code><small>Dừng/khởi động container bằng Docker Compose trên máy này.</small></> : <><small>Process mode: dừng và khởi động lại tiến trình bằng PowerShell, giữ nguyên thư mục dữ liệu. Không cần Docker.</small><code>HUONG_DAN_THUYET_TRINH.md · mục 4</code></>}</div>}
    <div className="kv-values">{names.map(name => {
      const node = state.nodes[name]
      const alive = state.services[name]?.alive
      const seqs = node?.group?.filter(row => row.stream === state.run?.id)
      const received = seqs?.map(row => row.seq) || []
      const missingSequences = Array.from({ length: Math.max(0, ...received) }, (_, index) => index + 1).filter(seq => !received.includes(seq))
      const displayed = page === 'rpc' ? node?.kv?.counter : page === 'recovery' ? node?.kv?.inventory : name === 'C' ? node?.kv?.last_transaction : node?.kv?.balance
      return <div key={name} data-testid={`kv-${name}`}><span><i className={alive ? 'live-dot' : 'dead-dot'} />{name === 'rpc' ? 'RPC Server' : `Node ${name}`}</span>{page === 'group' ? <><strong>{alive ? seqs?.filter(row => row.delivered).map(row => row.seq).join(' · ') || '—' : 'OFFLINE'}</strong><small>Received: {received.join(', ') || '—'} · Thiếu: {alive ? missingSequences.join(', ') || '—' : '?'}</small></> : <><strong title={String(displayed ?? '')}>{alive ? String(displayed ?? '—') : 'OFFLINE'}</strong><small>{page === 'rpc' ? 'counter' : page === 'recovery' ? 'inventory' : name === 'C' ? 'last_transaction' : 'balance'}{node?.locks?.length ? ' · LOCKED' : ''}</small></>}</div>
    })}</div>
    <div className="kv-verification" role="status">{result?.verified === true ? <><CheckCircle2 size={18} />Đã kiểm chứng bằng HTTP GET{page === 'rpc' && <> · {String(result.attempts)} attempts / {String(result.actual_executions)} executions</>}</> : <span>Chưa xác nhận kết quả toàn hệ thống</span>}{page === 'group' && state.run?.status === 'PARTIAL' && <button className="text-button" onClick={onCatchup}>Catch-up Node {catchup}</button>}</div>
  </div>
}

export function KVEditor({ state }: { state: Snapshot }) {
  const [node, setNode] = useState('rpc'), [key, setKey] = useState('counter'), [value, setValue] = useState('1')
  const [operation, setOperation] = useState('PUT'), [result, setResult] = useState<unknown>(null), [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const send = async (method: 'GET' | 'POST') => {
    setBusy(true); setError('')
    try {
      let parsed: unknown = value
      try { parsed = JSON.parse(value) } catch { /* Plain text is a valid KV string. */ }
      const response = await fetch(apiBase + '/kv/' + node + (method === 'GET' ? '/' + encodeURIComponent(key) : ''), { method, credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: method === 'POST' ? JSON.stringify({ key, operation, value: parsed }) : undefined })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'HTTP error')
      setResult(data)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  return <><h2>Đọc / ghi Key–Value</h2><p className="muted">HTTP tới worker riêng. Dữ liệu giữ qua restart; key PREPARED bị khóa.</p><div className="settings-fields">
    <label>Node<select aria-label="KV node" value={node} onChange={e => setNode(e.target.value)}>{['rpc', 'A', 'B', 'C'].map(id => <option key={id}>{id}</option>)}</select></label>
    <label>Key<input aria-label="KV key" value={key} maxLength={80} onChange={e => setKey(e.target.value)} /></label>
    <label>Phép ghi<select aria-label="KV operation" value={operation} onChange={e => setOperation(e.target.value)}><option>PUT</option><option>INCREMENT</option></select></label>
    <label>Value<input aria-label="KV value" value={value} onChange={e => setValue(e.target.value)} /></label>
    <button className="button secondary" disabled={busy || !key} onClick={() => void send('GET')}>GET</button><button className="button primary" disabled={busy || !key || !state.services[node]?.alive} onClick={() => void send('POST')}>Ghi KV</button>
  </div>{error && <p role="alert" className="red-text">{error}</p>}{result !== null && <pre data-testid="kv-http-result">{JSON.stringify(result, null, 2)}</pre>}</>
}

export function EventReplay({ state }: { state: Snapshot }) {
  const [recorded] = useState(() => [...state.events])
  const [index, setIndex] = useState(0), [playing, setPlaying] = useState(false), [speed, setSpeed] = useState(1000)
  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => setIndex(i => { if (i >= recorded.length - 1) { setPlaying(false); return i } return i + 1 }), speed)
    return () => clearInterval(timer)
  }, [playing, recorded.length, speed])
  const event = recorded[index]
  return <><span className="badge amber">REPLAY · nhật ký đã ghi</span><h2>Xem lại thông điệp</h2><p className="muted">Chỉ phát lại timeline, không gửi request và không tái tạo trạng thái node quá khứ.</p><div className="replay-controls"><button className="button primary" disabled={!recorded.length} onClick={() => { if (index === recorded.length - 1) setIndex(0); setPlaying(!playing) }}>{playing ? <Pause size={20} /> : <Play size={20} />}{playing ? 'Dừng replay' : 'Phát replay'}</button><button className="button secondary" disabled={index >= recorded.length - 1} onClick={() => setIndex(i => i + 1)}><SkipForward size={20} />Sự kiện tiếp</button><select aria-label="Tốc độ replay" value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value={1000}>1×</option><option value={500}>2×</option><option value={250}>4×</option></select></div>{event ? <><h3>{index + 1}/{recorded.length} · {event.source} → {event.target || 'local'} · {event.kind}</h3><pre>{JSON.stringify(event, null, 2)}</pre></> : <p>Chưa có sự kiện đã ghi.</p>}</>
}
