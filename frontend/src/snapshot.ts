import type { Snapshot } from './types'

function share<T>(previous: T, next: T): T {
  return previous === next || JSON.stringify(previous) === JSON.stringify(next) ? previous : next
}

/** Keep unchanged protocol data stable without dropping observations or events. */
export function reconcileSnapshot(previous: Snapshot, next: Snapshot): Snapshot {
  const nodes = Object.fromEntries(Object.entries(next.nodes).map(([id, node]) => [id, share(previous.nodes[id], node)]))
  const sameNodes = Object.keys(previous.nodes).length === Object.keys(nodes).length && Object.keys(nodes).every(id => nodes[id] === previous.nodes[id])
  return { ...next, nodes: sameNodes ? previous.nodes : nodes,
    run: share(previous.run, next.run), events: share(previous.events, next.events),
    transactions: share(previous.transactions, next.transactions), runtime: share(previous.runtime, next.runtime) }
}

/** Graphs do not display heartbeat timestamps; inspectors still receive them. */
export function sameDiagramSnapshot(previous: Snapshot, next: Snapshot): boolean {
  if (previous === next) return true
  if (previous.nodes !== next.nodes || previous.run !== next.run || previous.events !== next.events || previous.transactions !== next.transactions || previous.runtime !== next.runtime) return false
  const ids = Object.keys(next.services)
  return ids.length === Object.keys(previous.services).length && ids.every(id => {
    const old = previous.services[id], value = next.services[id]
    return old && old.alive === value.alive && old.pid === value.pid && old.port === value.port && old.boot_id === value.boot_id
  })
}
