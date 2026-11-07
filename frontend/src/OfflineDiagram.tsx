import { useEffect, useRef, useState } from 'react'
import { Database, Laptop, Layers, Minus, Monitor, Plus, Scan, Server, Workflow } from 'lucide-react'
import type { Page, Snapshot } from './types'
import { tone } from './types'
import { eventLabel, serviceData, useFreshEvents } from './topology'

export default function OfflineDiagram({ page, state, onInspect }: { page: Page; state: Snapshot; onInspect: (id: string) => void }) {
  const container = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 900, height: 420 })
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [offsets, setOffsets] = useState<Record<string, { x: number; y: number }>>({})
  const drag = useRef<{ id: string; x: number; y: number; ox: number; oy: number; moved: boolean } | null>(null)
  const fresh = useFreshEvents(state)
  useEffect(() => {
    const observer = new ResizeObserver(entries => setSize({ width: entries[0].contentRect.width, height: entries[0].contentRect.height }))
    if (container.current) observer.observe(container.current)
    return () => observer.disconnect()
  }, [])
  const compact = size.width < 470
  const boxes = serviceData(page, state).map((box, index) => ({ ...box,
    x: (compact ? 40 : box.x) + (offsets[box.id]?.x || 0),
    y: (compact ? 30 + index * 260 : box.y) + (offsets[box.id]?.y || 0),
  }))
  const worldWidth = compact ? 300 : 920
  const worldHeight = compact ? boxes.length * 260 : page === 'overview' ? 650 : page === 'rpc' ? 400 : 550
  const scale = Math.min((size.width - 28) / worldWidth, (size.height - 24) / worldHeight) * zoom
  const lines: { id: string; source: string; target: string; label: string; color: string; seq: number; reverse?: boolean; rpc?: boolean }[] = []
  if (page === 'rpc') {
    const request = [...state.events].reverse().find(e => ['SEND', 'RETRY', 'TIMEOUT', 'REQUEST_LOST', 'UNAVAILABLE'].includes(e.kind) && (e.source === 'Client' || e.target === 'A'))
    const response = [...state.events].reverse().find(e => ['ACK', 'RESPONSE_LOST'].includes(e.kind) && ['A', 'rpc'].includes(e.source))
    lines.push({ id: 'request', source: 'coordinator', target: 'A', rpc: true, seq: request?.seq || 0, label: !request ? 'Yêu cầu' : request.kind === 'SEND' ? `Request · ${String(request.data.operation_id || '').slice(-8)}` : eventLabel(request, state), color: request && /LOST|TIMEOUT|UNAVAILABLE/.test(request.kind) ? 'var(--red)' : 'var(--blue)' })
    lines.push({ id: 'response', source: 'A', target: 'coordinator', rpc: true, reverse: true, seq: response?.seq || 0, label: !response ? 'Chờ phản hồi' : response.kind === 'ACK' ? 'Response · OK' : 'Mất phản hồi', color: response?.kind === 'RESPONSE_LOST' ? 'var(--red)' : 'var(--green)' })
  } else for (const box of boxes.filter(b => !['coordinator', 'checkpoint', 'log'].includes(b.id))) {
    const event = [...state.events].reverse().find(e => (e.source === box.id || e.target === box.id) && ['SEND', 'ACK', 'VOTE', 'TIMEOUT', 'UNAVAILABLE', 'REQUEST_LOST', 'RETRANSMIT'].includes(e.kind))
    const reverse = event?.source === box.id
    lines.push({ id: box.id, source: box.id === 'rpc' && state.runtime ? reverse ? 'rpc' : 'web' : box.id === 'web' ? 'web' : reverse ? box.id : 'coordinator', target: box.id === 'rpc' && state.runtime ? reverse ? 'web' : 'rpc' : box.id === 'web' ? 'coordinator' : reverse ? 'coordinator' : box.id, reverse, label: box.id === 'web' ? state.runtime ? 'HTTP' : 'SSE' : event ? eventLabel(event, state) : 'HTTP', seq: event?.seq || 0, color: event && /LOST|TIMEOUT|UNAVAILABLE/.test(event.kind) ? 'var(--red)' : reverse ? 'var(--green)' : 'var(--blue)' })
  }
  if (page === 'recovery') for (const [id, kind] of [['checkpoint', 'CHECKPOINT'], ['log', 'RECOVERY']]) {
    const event = [...state.events].reverse().find(e => e.kind === kind)
    lines.push({ id, source: 'A', target: id, label: event ? `#${event.seq}` : '—', seq: event?.seq || 0, color: 'var(--blue)' })
  }
  const end = () => { const current = drag.current; drag.current = null; if (current && !current.moved && current.id !== 'pan') onInspect(current.id) }
  return <div ref={container} className="diagram offline-diagram" data-renderer="svg"
    onPointerDown={event => { if (event.target === event.currentTarget) { event.currentTarget.setPointerCapture(event.pointerId); drag.current = { id: 'pan', x: event.clientX, y: event.clientY, ox: pan.x, oy: pan.y, moved: false } } }}
    onPointerMove={event => {
      const current = drag.current
      if (!current) return
      const dx = event.clientX - current.x, dy = event.clientY - current.y
      if (Math.abs(dx) + Math.abs(dy) > 4) current.moved = true
      if (current.id === 'pan') setPan({ x: current.ox + dx, y: current.oy + dy })
      else setOffsets(value => ({ ...value, [current.id]: { x: current.ox + dx / scale, y: current.oy + dy / scale } }))
    }} onPointerUp={end} onPointerCancel={() => { drag.current = null }}>
    <div className="offline-world" style={{ width: worldWidth, height: worldHeight, transform: `translate(${(size.width - worldWidth * scale) / 2 + pan.x}px,${(size.height - worldHeight * scale) / 2 + pan.y}px) scale(${scale})` }}>
      <svg className="offline-edges" width={worldWidth} height={worldHeight}><defs><marker id="offline-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="context-stroke" /></marker></defs>
        {lines.map(line => {
          const from = boxes.find(box => box.id === line.source)!, to = boxes.find(box => box.id === line.target)!
          const horizontal = line.rpc && !compact
          const resource = !compact && ['checkpoint', 'log'].includes(line.target)
          const x1 = from.x + (resource ? 220 : horizontal ? line.reverse ? 0 : 220 : 110)
          const x2 = to.x + (resource ? 0 : horizontal ? line.reverse ? 220 : 0 : 110)
          const y1 = from.y + (resource ? 60 : horizontal ? line.reverse ? 143 : 60 : line.reverse ? 0 : 200)
          const y2 = to.y + (resource ? 60 : horizontal ? line.reverse ? 143 : 60 : line.reverse ? 200 : 0)
          const middle = (y1 + y2) / 2
          const path = horizontal ? `M${x1} ${y1} Q${(x1 + x2) / 2} ${middle + (line.reverse ? 70 : -70)} ${x2} ${y2}` : `M${x1} ${y1} V${middle} H${x2} V${y2}`
          const labelX = horizontal || ['checkpoint', 'log'].includes(line.target) || !(line.reverse ? y1 > y2 : y2 > y1) ? (x1 + x2) / 2 : line.reverse ? x1 : x2, labelY = middle + (horizontal ? line.reverse ? 70 : -70 : 0)
          const width = horizontal ? 260 : ['checkpoint', 'log'].includes(line.target) ? 80 : 170
          return <g key={line.id}><path d={path} fill="none" stroke={line.color} strokeWidth={3} strokeDasharray={line.seq ? undefined : '7 6'} opacity={line.seq ? 1 : .5} markerEnd="url(#offline-arrow)" /><g className="message-label" transform={`translate(${labelX},${labelY})`}><rect x={-width / 2} y={-22} width={width} height={44} rx={22} /><text textAnchor="middle" dy="6" fill={line.color}>{line.label}</text></g>{fresh.includes(line.seq) && <circle className="message-pulse" r={6} fill={line.color} key={line.seq}><animateMotion dur=".8s" repeatCount="1" path={path} /></circle>}</g>
        })}
      </svg>
      {boxes.map(box => {
        const Icon = box.id === 'checkpoint' ? Database : box.id === 'log' ? Layers : box.id === 'web' ? Monitor : box.id === 'coordinator' ? page === 'rpc' ? Laptop : Workflow : Server
        return <button key={box.id} className={`service-node ${box.id === 'coordinator' || box.id === 'web' ? 'client-node' : 'server-node'} ${tone(box.status)}`} style={{ left: box.x, top: box.y, touchAction: 'none' }} aria-label={`Kiểm tra ${box.title}`}
          onPointerDown={event => { event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId); drag.current = { id: box.id, x: event.clientX, y: event.clientY, ox: offsets[box.id]?.x || 0, oy: offsets[box.id]?.y || 0, moved: false } }}
          onClick={event => { if (event.detail === 0) onInspect(box.id) }}>
          <span className="node-icon"><Icon size={48} strokeWidth={1.8} /></span><strong>{box.title}</strong><span className={`node-status ${['ONLINE', 'DELIVERED', 'DURABLE'].includes(box.status) ? 'green' : tone(box.status)}`}>{box.status}</span>{box.value && <span className="node-value" data-testid={page === 'rpc' && box.id === 'A' ? 'rpc-executions' : undefined}>{box.value}</span>}
        </button>
      })}
    </div>
    <div className="offline-controls"><button aria-label="Phóng to sơ đồ" onClick={() => setZoom(value => Math.min(1.8, value + .15))}><Plus size={16} /></button><button aria-label="Thu nhỏ sơ đồ" onClick={() => setZoom(value => Math.max(.4, value - .15))}><Minus size={16} /></button><button aria-label="Căn vừa sơ đồ" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); setOffsets({}) }}><Scan size={16} /></button></div>
  </div>
}
