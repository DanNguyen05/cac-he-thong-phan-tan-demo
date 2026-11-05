import { useEffect, useRef, useState } from 'react'
import type { LogEvent, Page, Snapshot } from './types'

export function eventLabel(event: LogEvent, state: Snapshot) {
  if (event.kind === 'VOTE') return `VOTE ${event.data.vote}`
  if (event.kind === 'SEND') {
    const path = String(event.data.path)
    return ({ '/rpc': 'REQUEST', '/multicast': 'MULTICAST', '/prepare': 'PREPARE',
      '/decision': state.transactions[0]?.state || 'DECISION', '/operation': 'WRITE LOG',
      '/checkpoint': 'CHECKPOINT', '/recover': 'REPLAY' } as Record<string, string>)[path] || path
  }
  if (event.kind === 'ACK' && event.data.path === '/rpc') return 'RESPONSE'
  return event.kind
}

export function serviceData(page: Page, state: Snapshot) {
  const wide = ['overview', 'group', 'commit'].includes(page)
  const coordinator = state.services.coordinator
  const list: { id: string; x: number; y: number; title: string; role: string; status: string; value: string; pid?: number; port?: number }[] = [{ id: 'coordinator', x: wide ? 310 : 60, y: page === 'overview' ? 190 : wide ? 35 : 115,
    title: page === 'rpc' ? 'RPC Client' : page === 'group' ? 'Group Sender' : 'Coordinator',
    role: page === 'rpc' ? 'Bên gọi thủ tục' : page === 'group' ? 'Multicast sender' : 'Điều phối giao dịch',
    status: coordinator ? coordinator.alive ? state.transactions[0]?.state || 'ONLINE' : 'CRASHED' : 'UNKNOWN',
    value: 'Durable event journal', pid: coordinator?.pid, port: coordinator?.port }]
  if (page === 'overview') list.unshift({ id: 'web', x: 310, y: 0, title: 'Web Client', role: 'React · SSE subscriber', status: 'BROWSER', value: 'API gateway / SSE', pid: undefined, port: undefined })
  ;(wide ? ['A', 'B', 'C'] : ['A']).forEach((name, index) => {
    const node = state.nodes[name]
    let status = !node ? 'UNKNOWN' : node.crashed ? 'CRASHED' : node.unreachable ? 'UNREACHABLE' : node.available ? 'ONLINE' : 'UNAVAILABLE'
    if (node?.available && page === 'commit') status = node.transactions?.[0]?.state || 'IDLE'
    if (node?.available && page === 'group') status = node.multicast?.length ? 'DELIVERED' : 'AWAITING DELIVERY'
    list.push({ id: name, x: wide ? 20 + index * 290 : 530, y: page === 'overview' ? 410 : wide ? 300 : 115,
      title: `Node ${name}`, role: page === 'commit' ? 'Participant · SQLite' : page === 'rpc' ? 'RPC server · SQLite' : page === 'group' ? 'Group member · SQLite' : 'Recovery worker · SQLite', status,
      value: page === 'rpc' ? `${node?.counters?.rpc ?? '—'} lần thực thi` : page === 'group' ? `${node?.multicast?.length ?? '—'} thông điệp đã giao` : page === 'commit' ? `Số dư: ${node?.counters?.commit ?? '—'}` : page === 'recovery' ? `State: ${node?.memory_value ?? '—'} · CP: ${node?.checkpoint?.value ?? '—'}` : 'SQLite · ổ đĩa riêng',
      pid: node?.pid, port: state.services[name]?.port,
    })
  })
  if (page === 'rpc') {
    list[0] = { ...list[0], x: 20, y: 100, title: 'Client', role: 'client', value: '' }
    list[1] = { ...list[1], x: 620, y: 100, title: 'Server', role: 'server', value: `Thực thi: ${state.nodes.A?.counters?.rpc ?? '—'} lần` }
  }
  if (page === 'group') list[0] = { ...list[0], title: 'Sender', value: 'Multicast' }
  if (page === 'recovery') {
    list[0] = { ...list[0], x: 0, y: 135, title: 'Recovery', value: '' }
    list[1] = { ...list[1], x: 330, y: 135, value: `State: ${state.nodes.A?.memory_value ?? '—'}` }
    const node = state.nodes.A
    list.push({ id: 'checkpoint', x: 680, y: 0, title: 'Checkpoint', role: 'resource', status: node?.checkpoint ? 'DURABLE' : 'UNKNOWN', value: `Value: ${node?.checkpoint?.value ?? '—'} · #${node?.checkpoint?.seq ?? '—'}` })
    list.push({ id: 'log', x: 680, y: 290, title: 'Redo log', role: 'resource', status: node?.operations ? 'DURABLE' : 'UNKNOWN', value: `${node?.operations?.length ?? '—'} ops · ${node?.recovery?.replayed?.length ?? '—'} replay` })
  }
  return list.map(item => ({ ...item, page }))
}

export function useFreshEvents(state: Snapshot) {
  const [fresh, setFresh] = useState<number[]>([])
  const previous = useRef<{ run: string | undefined; seq: number }>({ run: undefined, seq: 0 })
  const last = state.events.at(-1)?.seq || 0
  useEffect(() => {
    const old = previous.current
    if (old.run === state.run?.id && old.seq > 0 && last > old.seq) {
      setFresh(state.events.filter(e => e.seq > old.seq).map(e => e.seq))
    } else setFresh([])
    previous.current = { run: state.run?.id, seq: last }
    const timer = window.setTimeout(() => setFresh([]), 1100)
    return () => window.clearTimeout(timer)
  }, [last, state.run?.id]) // Only new journal events trigger a finite pulse.
  return fresh
}

export function useMessages(state: Snapshot) {
  const fresh = useFreshEvents(state)
  const messages = ['A', 'B', 'C'].flatMap(name => {
    const event = [...state.events].reverse().find(e =>
      (e.source === name || e.target === name) && ['SEND', 'ACK', 'TIMEOUT', 'RETRY', 'REQUEST_LOST', 'RESPONSE_LOST', 'VOTE', 'UNAVAILABLE', 'RETRANSMIT'].includes(e.kind))
    return event ? [{ node: name, event, fresh: fresh.includes(event.seq), reverse: event.source === name }] : []
  })
  return messages
}
