import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Catalog, LogEvent, Module, Page, Snapshot } from './types'
import { EMPTY } from './types'
import { modules } from './content'
import { apiBase, eventURL, post } from './api'
import { reconcileSnapshot } from './snapshot'
import { runControls } from './runControls'

function routePage(): Page {
  const value = location.pathname.split("/").filter(Boolean).at(-1)
  return value && value in modules ? value as Module : 'overview'
}

export default function useLab() {
  const [state, setState] = useState<Snapshot>(EMPTY)
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [page, setPage] = useState<Page>(routePage)
  const [connected, setConnected] = useState(false)
  const [presentation, setPresentation] = useState(false)
  const [scenario, setScenario] = useState('normal')
  const [mode, setMode] = useState('auto')
  const [pace, setPace] = useState(600)
  const [receivedAt, setReceivedAt] = useState(0)
  const receivedRef = useRef(0)
  const [deduplicate, setDeduplicate] = useState(true)
  const [retry, setRetry] = useState(true)
  const [maxAttempts, setMaxAttempts] = useState(3)
  const [target, setTarget] = useState('B')
  const [delay, setDelay] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [inspectNode, setInspectNode] = useState<string | null>(null)
  const [inspectEvent, setInspectEvent] = useState<LogEvent | null>(null)
  const [help, setHelp] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const lastRunId = useRef<string | null>(null)

  useEffect(() => {
    fetch(apiBase + '/catalog', { credentials: 'include' }).then(r => { if (!r.ok) throw new Error('Không tải được danh sách kịch bản'); return r.json() }).then(setCatalog).catch(e => setError(String(e)))
    const source = new EventSource(eventURL, { withCredentials: true })
    source.addEventListener('snapshot', (event: MessageEvent) => { const next = JSON.parse(event.data) as Snapshot; setState(previous => reconcileSnapshot(previous, next)); setConnected(true); receivedRef.current = Date.now(); setReceivedAt(receivedRef.current) })
    source.onerror = () => setConnected(false)
    const timer = window.setInterval(() => { if (Date.now() - receivedRef.current > 10000) setConnected(false) }, 2000)
    return () => { source.close(); window.clearInterval(timer) }
  }, [])

  useEffect(() => {
    if (state.run?.id !== lastRunId.current) { setSelected(null); lastRunId.current = state.run?.id ?? null }
  }, [state.run?.id])

  const act = useCallback(async (path: string, body?: unknown) => {
    setBusy(true); setError('')
    try { await post(path, body) } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
  }, [])

  useEffect(() => {
    const pop = () => { setPage(routePage()); setScenario('normal'); setSelected(null) }
    window.addEventListener('popstate', pop)
    return () => window.removeEventListener('popstate', pop)
  }, [])
  const navigate = (next: Page) => {
    history.pushState({}, '', next === 'overview' ? '/' : '/' + next)
    setPage(next); setScenario('normal'); setSelected(null)
  }
  const { running, unresolved, externalWait } = runControls(state)
  const paused = state.run?.config.paused === true
  const canPause = running && state.run?.config.mode === 'auto' && !externalWait
  const current = page === 'overview' || state.run?.module === page
  const display = useMemo<Snapshot>(() => current ? state : { ...state, run: null, events: EMPTY.events, transactions: EMPTY.transactions }, [current, state])
  const latest = display.events.find(event => event.seq === selected) || display.events.at(-1)
  const module = page === 'overview' ? null : modules[page]
  const liveCount = Object.values(state.services).filter(s => s.alive).length
  const rpcCount = state.nodes.A?.counters?.rpc ?? '—'
  const faultCount = state.events.filter(e => /LOST|CRASH|TIMEOUT|UNAVAILABLE/.test(e.kind)).length

  const start = () => { if (page !== 'overview') void act('/runs', { module: page, scenario, mode, deduplicate, retry, max_attempts: maxAttempts, target, delay_ms: delay, pace_ms: pace }) }

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing) return
      if (event.key === 'Escape') {
        setPresentation(false); setHelp(false); setInspectNode(null); setInspectEvent(null)
        return
      }
      if (event.altKey || event.ctrlKey || event.metaKey || event.repeat) return
      if ((event.target as HTMLElement).closest('input, select, textarea, [contenteditable]:not([contenteditable="false"]), [role="textbox"]')) return
      if (help || inspectNode || inspectEvent) return
      if (event.key.toLowerCase() === 'n' && connected && state.run?.status === 'WAITING' && !externalWait && !busy) {
        event.preventDefault()
        void act('/step')
      }
      if (event.key.toLowerCase() === 'p' && connected && canPause && !busy) {
        event.preventDefault()
        void act('/control', { paused: !paused })
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [act, busy, connected, help, inspectNode, inspectEvent, state.run?.status, canPause, paused, externalWait])

  const selectEvent = (event: LogEvent) => { setSelected(event.seq); setInspectEvent(event) }
  const exportLog = () => {
    const anchor = document.createElement('a')
    anchor.href = URL.createObjectURL(new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' }))
    anchor.download = `fault-lab-${state.run?.id.slice(0, 8) || 'snapshot'}.json`; anchor.click(); URL.revokeObjectURL(anchor.href)
  }

  return { state, catalog, page, connected, presentation, setPresentation, scenario, setScenario, mode, setMode, pace, setPace, receivedAt, deduplicate, setDeduplicate, retry, setRetry, maxAttempts, setMaxAttempts, target, setTarget, delay, setDelay, busy, error, setError, inspectNode, setInspectNode, inspectEvent, setInspectEvent, help, setHelp, selected, act, navigate, running, paused, canPause, unresolved, current, display, latest, module, liveCount, rpcCount, faultCount, start, selectEvent, exportLog }
}
