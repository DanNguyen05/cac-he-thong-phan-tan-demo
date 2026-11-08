import { useCallback, useState } from 'react'
import { Box, CheckCircle2, ChevronRight, CircleHelp, Download, Gauge, Info, LayoutDashboard, Maximize2, Minimize2, Pause, Play, RefreshCw, Settings, SkipForward, Target, X, Zap } from 'lucide-react'
import type { Module } from './types'
import { tone } from './types'
import { modules } from './content'
import useLab from './useLab'
import Diagram from './Diagram'
import EventLog from './EventLog'
import Sequence from './Sequence'
import Modal from './Modal'
import ProtocolState from './ProtocolState'
import { CompactTimeline, LabMetrics } from './LabSummary'
import KVWorkbench, { KVEditor, EventReplay } from './KVWorkbench'

const screens: Record<Module, { title: string; short: string; subtitle: string }> = {
  rpc: { title: 'Giao tiếp Client – Server', short: 'Client–Server', subtitle: 'Minh họa RPC tin cậy, retry và xử lý trùng lặp' },
  group: { title: 'Giao tiếp nhóm tin cậy', short: 'Group Comm.', subtitle: 'Multicast, ACK và truyền lại tới node chưa nhận' },
  commit: { title: 'Cam kết phân tán', short: 'Distributed Commit', subtitle: 'Two-Phase Commit: cùng quyết định, cùng trạng thái' },
  recovery: { title: 'Phục hồi sau sự cố', short: 'Recovery', subtitle: 'Checkpoint, nhật ký và khôi phục trạng thái' },
}
const faults: Record<Module, { id: string; label: string }[]> = {
  rpc: [{ id: 'lost_request', label: 'Mất yêu cầu' }, { id: 'lost_response', label: 'Mất phản hồi' }, { id: 'server_down', label: 'Server không hoạt động' }],
  group: [{ id: 'lost_message', label: 'Mất thông điệp' }, { id: 'duplicate', label: 'Gửi lặp thông điệp' }, { id: 'node_down', label: 'Một node không khả dụng' }],
  commit: [{ id: 'vote_no', label: 'Một phiếu NO' }, { id: 'participant_crash', label: 'Participant dừng' }, { id: 'coordinator_crash', label: 'Coordinator dừng' }],
  recovery: [{ id: 'checkpoint', label: 'Tạo checkpoint' }, { id: 'crash_recover', label: 'Crash và khôi phục' }, { id: 'idempotent', label: 'Phát lại nhiều lần' }],
}

export default function App() {
  const lab = useLab()
  const { page, state, display } = lab
  const [pane, setPane] = useState<'settings' | 'journal' | 'sequence' | 'help' | 'kv' | 'replay'>('settings')
  const [renderer, setRenderer] = useState<'reactflow' | 'svg'>(() => new URLSearchParams(location.search).get('renderer') === 'svg' || import.meta.env.VITE_DEFAULT_RENDERER === 'svg' ? 'svg' : 'reactflow')
  const module = page === 'overview' ? null : modules[page]
  const screen = page === 'overview' ? null : screens[page]
  const status = display.run?.status
  const connected = lab.connected
  const isKV = state.runtime?.mode === 'kv'
  const serviceCount = state.runtime?.services || 4
  const healthy = connected && lab.liveCount === serviceCount
  const externalWait = lab.running && isKV && ['AWAIT_CONTAINER_RESTART', 'AWAIT_RPC_STOP', 'AWAIT_RECEIVER_STOP'].includes(String(display.run?.result?.stage))
  const faultList = page === 'overview' ? [] : isKV && page === 'commit' ? [{ id: 'vote_no', label: 'Một phiếu NO' }, { id: 'coordinator_crash', label: 'Dừng sau PREPARED' }, { id: 'coordinator_after_commit', label: 'Dừng sau ghi COMMIT' }] : faults[page]
  const canConfigure = !lab.running && !lab.unresolved && !lab.busy
  const open = (next: typeof pane) => { setPane(next); lab.setHelp(true) }
  const close = () => { lab.setHelp(false); lab.setInspectNode(null); lab.setInspectEvent(null) }
  const inspect = useCallback((id: string) => lab.setInspectNode(['checkpoint', 'log'].includes(id) ? 'A' : isKV && page === 'rpc' && id === 'A' ? 'rpc' : isKV && ['rpc', 'group', 'recovery'].includes(page) && id === 'coordinator' ? 'gateway' : isKV && id === 'web' ? 'gateway' : id), [isKV, page, lab.setInspectNode])
  const runLabel = lab.canPause ? lab.paused ? 'Tiếp tục' : 'Tạm dừng' : 'Chạy thí nghiệm'
  const resultDecision = display.transactions[0]?.state
  const statusLabel = !connected ? 'Đang kết nối…' : !lab.current && state.run ? 'Có thí nghiệm đang giữ' :
    !status ? 'Sẵn sàng chạy' : status === 'WAITING' ? externalWait ? 'Chờ thao tác bên ngoài' : 'Chờ bước tiếp theo' :
    status === 'RUNNING' ? 'Đang thực hiện…' : status === 'BLOCKED' ? '2PC đang blocking' :
    status === 'DECISION_PENDING' ? 'Chờ xác nhận quyết định' : status === 'INTERRUPTED' ? 'Tiến trình bị gián đoạn' :
    status === 'COMPLETED' ? resultDecision === 'ABORT' ? 'Giao dịch đã ABORT' : 'Hoàn thành thành công' :
    status === 'PARTIAL' ? 'Một số node chưa nhận' : 'Thí nghiệm thất bại'
  const statusTone = !status ? 'blue' : status === 'COMPLETED' && resultDecision === 'ABORT' ? 'amber' : tone(status)
  const stepButton = () => {
    if (lab.running && status === 'WAITING') void lab.act('/step')
    else lab.setMode(lab.mode === 'step' ? 'auto' : 'step')
  }
  const presentationButton = <button className="button secondary presentation-toggle" onClick={() => lab.setPresentation(!lab.presentation)}>
    {lab.presentation ? <Minimize2 size={22} /> : <Maximize2 size={22} />}{lab.presentation ? 'Thoát trình chiếu' : 'Trình chiếu'}
  </button>

  return <div className={`app ${lab.presentation ? 'presentation' : ''}`}>
    <a className="skip-link" href="#main-content">Bỏ qua điều hướng</a>
    <aside className="sidebar">
      <a className="brand" href="/" onClick={event => { event.preventDefault(); lab.navigate('overview') }}><Box size={43} strokeWidth={1.8} /><span><strong>{isKV ? 'Distributed KV Lab' : 'Fault Tolerance Lab'}</strong><small>{isKV ? 'Transactions / Fault Tolerance' : 'Distributed Systems'}</small></span></a>
      <nav aria-label="Điều hướng chính">
        <button className={`nav-item ${page === 'overview' ? 'active' : ''}`} title="Tổng quan" aria-current={page === 'overview' ? 'page' : undefined} onClick={() => lab.navigate('overview')}><LayoutDashboard size={25} /><span>Tổng quan</span></button>
        {(Object.entries(modules) as [Module, typeof modules.rpc][]).map(([key, value]) => <button key={key} className={`nav-item ${page === key ? 'active' : ''}`} title={`${value.section} ${value.title}`} aria-current={page === key ? 'page' : undefined} onClick={() => lab.navigate(key)}><value.icon size={25} /><span><b>{value.section}</b> {screens[key].short}</span></button>)}
      </nav>
      <div className="sidebar-status"><i className={healthy ? 'live-dot' : 'warning-dot'} /><div><strong>{connected ? 'Hệ thống hoạt động' : 'Đang kết nối'}</strong><span>{connected ? `${lab.liveCount}/${serviceCount} service online` : 'Chờ dữ liệu backend'}</span></div></div>
    </aside>

    <div className="workspace">
      <header className="topbar"><div className="breadcrumbs"><strong>{isKV ? 'Distributed KV Transaction Lab' : 'Fault Tolerance Lab'}</strong><ChevronRight size={20} /><span>{module ? `${module.section} ${screen?.short}` : 'Tổng quan'}</span></div>
        <div className="top-actions"><span className={`connection ${healthy ? 'green' : 'amber'}`} data-testid="connection" data-connected={connected} title={lab.receivedAt ? `Cập nhật ${new Date(lab.receivedAt).toLocaleTimeString('vi-VN')}` : 'Chờ SSE'}><i className={healthy ? 'live-dot' : 'warning-dot'} />{connected ? healthy ? 'Hệ thống Online' : `${lab.liveCount}/${serviceCount} service Online` : 'Mất kết nối'}</span>{presentationButton}<button className="icon-button settings-trigger" aria-label="Cài đặt" title="Cài đặt & trợ giúp" onClick={() => open('settings')}><Settings size={24} /></button></div>
      </header>

      <main id="main-content" className={`reference-workspace page-${page}`}>
        <div className="page-heading"><div><h1>{module && <span className="chapter-badge">{module.section}</span>}{screen?.title || 'Khả năng chịu lỗi'}</h1><p>{screen?.subtitle || 'Chọn một thí nghiệm. Chạy và quan sát hệ thống.'}</p></div>{lab.presentation && <div className="presentation-actions">{presentationButton}<button className="icon-button" aria-label="Cài đặt" onClick={() => open('settings')}><Settings size={24} /></button></div>}</div>
        {lab.error && <div className="error-banner" role="alert"><X size={20} /><span>{lab.error}</span><button className="icon-button" aria-label="Đóng thông báo" onClick={() => lab.setError('')}><X size={18} /></button></div>}
        <LabMetrics page={page} state={display} connected={connected} />

        <section className="panel topology-panel">
          <div className="section-heading"><h2><i className={connected ? 'live-dot' : 'warning-dot'} />{page === 'overview' ? 'Kiến trúc hệ thống' : page === 'commit' ? 'Sơ đồ Two-Phase Commit' : page === 'recovery' ? 'Checkpoint & phục hồi' : 'Sơ đồ giao tiếp'}<span className="muted">(Live)</span></h2><button className="icon-button" aria-label={page === 'commit' ? 'Xem sơ đồ trình tự' : 'Xem nguyên lý giao thức'} title="Xem chi tiết" onClick={() => open(page === 'commit' ? 'sequence' : 'help')}><Info size={21} /></button></div>
          {page === 'commit' && <div className={`protocol-phases ${status === 'BLOCKED' ? 'blocked' : ''}`} aria-label="Các pha 2PC"><span>1 <b>PREPARE</b></span><ChevronRight size={16} /><span>2 <b>VOTE</b></span><ChevronRight size={16} /><span>3 <b>{status === 'BLOCKED' ? 'BLOCKED' : ['COMMIT', 'ABORT'].includes(resultDecision || '') ? resultDecision : 'DECISION'}</b></span></div>}
          <Diagram page={page} state={display} onInspect={inspect} renderer={renderer} />
          {isKV && <KVWorkbench state={display} page={page} onEdit={() => open('kv')} onCatchup={() => void lab.act('/group/catchup', { target: Array.isArray(display.run?.result?.missing_nodes) ? display.run.result.missing_nodes[0] : display.run?.config.target || 'B' })} />}
        </section>

        <CompactTimeline events={display.events} onSelect={lab.selectEvent} onOpen={() => open('journal')} onReplay={isKV ? () => open('replay') : undefined} />

        {page === 'overview' ? <aside className="panel control-panel module-picker"><h2><Target size={25} />Chọn thí nghiệm</h2>{(Object.keys(modules) as Module[]).map(key => <button className="module-choice" key={key} onClick={() => lab.navigate(key)}><span>{modules[key].section}</span><strong>{screens[key].short}</strong><ChevronRight size={20} /></button>)}<div className="quick-start"><span>1. Chọn kịch bản</span><span>2. Chạy thí nghiệm</span><span>3. Quan sát kết quả</span></div></aside> :
        <aside className="panel control-panel" aria-label="Điều khiển thí nghiệm">
          <div className="control-section scenario-section"><label className="section-title" htmlFor="scenario"><Target size={25} />Kịch bản thí nghiệm</label><select id="scenario" value={lab.scenario} disabled={!canConfigure} onChange={event => lab.setScenario(event.target.value)}>{lab.catalog?.[page].map(([id, title]) => <option key={id} value={id}>{title}</option>) || <option value="normal">Đang tải kịch bản…</option>}</select></div>
          <div className="control-section action-section">
            <button className="button primary run-button" disabled={!connected || !lab.catalog || lab.busy || lab.unresolved || (lab.running && !lab.canPause)} onClick={() => { if (lab.canPause) void lab.act('/control', { paused: !lab.paused }); else lab.start() }}>{lab.canPause && !lab.paused ? <Pause size={25} /> : <Play size={25} />}{runLabel}</button>
            <div className="secondary-actions"><button className={`button secondary step-button ${lab.mode === 'step' && !lab.running ? 'selected' : ''}`} aria-pressed={lab.mode === 'step'} disabled={!connected || lab.busy || lab.unresolved || externalWait || (lab.running && status !== 'WAITING')} onClick={stepButton}><SkipForward size={23} />{lab.running && status === 'WAITING' ? 'Bước tiếp' : 'Từng bước'}{lab.running && status === 'WAITING' && <kbd>N</kbd>}</button><button className="button secondary" disabled={!connected || lab.busy} onClick={() => void lab.act('/reset')}><RefreshCw size={23} />Đặt lại</button></div>
          </div>
          <div className="control-section speed-section"><h2><Gauge size={24} />Tốc độ</h2><div className="speed-options" role="group" aria-label="Tốc độ thực thi">{[{ value: 1200, label: '0.5×' }, { value: 600, label: '1×' }, { value: 300, label: '2×' }].map(speed => <button key={speed.value} className={(lab.running ? Number(state.run?.config.pace_ms) : lab.pace) === speed.value ? 'active' : ''} aria-pressed={(lab.running ? Number(state.run?.config.pace_ms) : lab.pace) === speed.value} disabled={lab.busy || lab.unresolved} onClick={() => { lab.setPace(speed.value); if (lab.running) void lab.act('/control', { pace_ms: speed.value }) }}>{speed.label}</button>)}</div></div>
          <div className="control-section"><div className="fault-options"><h2><Zap size={24} />{isKV ? 'Chế độ lỗi' : 'Mô phỏng lỗi'}</h2>{faultList.map(fault => <label className="fault-switch" key={fault.id}><span>{fault.label}</span><input type="checkbox" role="switch" aria-label={fault.label} checked={lab.scenario === fault.id} disabled={!canConfigure} onChange={event => lab.setScenario(event.target.checked ? fault.id : 'normal')} /><i aria-hidden="true" /></label>)}</div></div>
          <div className="control-section status-section"><div className={`current-status ${statusTone}`} role="status" aria-live="polite" data-testid="current-status"><h2><CheckCircle2 size={23} />Trạng thái hiện tại</h2><strong>{statusLabel}</strong>{status === 'BLOCKED' && <span>Participant giữ PREPARED</span>}{status === 'WAITING' && !externalWait && <span>Nhấn N hoặc Bước tiếp</span>}{externalWait && <span>Xem lệnh trong vùng KV</span>}</div>
            {lab.current && lab.unresolved && display.transactions.length > 0 && !isKV && <button className="button primary resolve-button" disabled={lab.busy || !connected} onClick={() => void lab.act('/resolve')}><RefreshCw size={21} />Khởi động & phục hồi</button>}
            {isKV && lab.unresolved && <p className="docker-hint">Khởi động service bằng CLI. Coordinator tự phục hồi durable log.</p>}
            {status === 'INTERRUPTED' && !lab.unresolved && <p className="docker-hint" role="note">Lần chạy trước đã dừng. Chọn kịch bản rồi Chạy thí nghiệm để bắt đầu lại; dữ liệu KV vẫn được giữ.</p>}
            {!lab.current && state.run && <button className="text-button" onClick={() => lab.navigate(state.run!.module)}>Mở thí nghiệm đang giữ</button>}
          </div>
        </aside>}
      </main>
    </div>

    {(lab.help || lab.inspectNode || lab.inspectEvent) && <Modal label={lab.inspectEvent ? 'Chi tiết sự kiện' : lab.inspectNode ? 'Trạng thái node' : pane === 'journal' ? 'Nhật ký đầy đủ' : pane === 'sequence' ? 'Sơ đồ trình tự' : pane === 'help' ? 'Hướng dẫn' : pane === 'kv' ? 'Dữ liệu KV' : pane === 'replay' ? 'Replay nhật ký' : 'Cài đặt'} onClose={close}>
      {lab.inspectEvent ? <><span className={`badge ${tone(lab.inspectEvent.kind)}`}>{lab.inspectEvent.kind}</span><h2>Sự kiện #{lab.inspectEvent.seq}</h2><p>{lab.inspectEvent.detail}</p><pre>{JSON.stringify(lab.inspectEvent, null, 2)}</pre></> : lab.inspectNode ? <NodeInspector id={lab.inspectNode} lab={lab} /> :
      pane === 'kv' ? <KVEditor state={state} /> : pane === 'replay' ? <EventReplay state={display} /> :
      pane === 'journal' ? <><h2>Nhật ký đầy đủ</h2><EventLog state={display} selected={lab.selected} onSelect={lab.selectEvent} /></> :
      pane === 'sequence' ? <><h2>Two-Phase Commit</h2><Sequence events={display.events} onSelect={lab.selectEvent} /></> :
      pane === 'help' ? <><h2>{screen?.title || 'Bắt đầu thí nghiệm'}</h2><ol className="help-list"><li>Chọn kịch bản và nhấn <b>Chạy thí nghiệm</b>.</li><li>Chọn <b>Từng bước</b> trước khi chạy để dùng phím <kbd>N</kbd>.</li><li>Phím <kbd>P</kbd> tạm dừng / tiếp tục tự động. <kbd>Esc</kbd> đóng hộp thoại hoặc thoát trình chiếu.</li></ol>{module && <><h3>Nguyên lý</h3><p>{module.theory}</p><h3>Giới hạn</h3><p>{module.limit}</p></>}</> :
      <><h2>Cài đặt thí nghiệm</h2><div className="settings-fields">
        <label>Bộ hiển thị<select aria-label="Bộ hiển thị" value={renderer} onChange={event => setRenderer(event.target.value as typeof renderer)}>{import.meta.env.VITE_DEFAULT_RENDERER !== 'svg' && <option value="reactflow">React Flow</option>}<option value="svg">SVG dự phòng</option></select></label>
        {page === 'rpc' && <><label className="check-label"><input aria-label="Khử trùng lặp" type="checkbox" checked={lab.deduplicate} disabled={!canConfigure} onChange={event => lab.setDeduplicate(event.target.checked)} />Khử trùng lặp</label><label className="check-label"><input aria-label="Thử lại khi lỗi" type="checkbox" checked={lab.retry} disabled={!canConfigure} onChange={event => lab.setRetry(event.target.checked)} />Thử lại khi lỗi</label></>}
        {(page === 'group' || page === 'commit') && <label>Node gây lỗi<select aria-label="Node gây lỗi" value={lab.target} disabled={!canConfigure} onChange={event => lab.setTarget(event.target.value)}>{['A', 'B', 'C'].map(id => <option key={id} value={id}>Node {id}</option>)}</select></label>}
        {page !== 'recovery' && (!isKV || page === 'rpc') && <><label>Số lần thử tối đa<select aria-label="Số lần thử tối đa" value={lab.maxAttempts} disabled={!canConfigure} onChange={event => lab.setMaxAttempts(Number(event.target.value))}>{[1, 2, 3, 4, 5].map(value => <option key={value}>{value}</option>)}</select></label>{!isKV && <label>Độ trễ transport · {lab.delay} ms<input aria-label="Độ trễ transport" type="range" min="0" max="1500" step="100" disabled={!canConfigure} value={lab.delay} onChange={event => lab.setDelay(Number(event.target.value))} /></label>}</>}
        <button className="button secondary" onClick={() => open('help')}><CircleHelp size={20} />Hướng dẫn nhanh</button><button className="button secondary" onClick={lab.exportLog}><Download size={20} />Xuất snapshot JSON</button>
        {page !== 'overview' && <details><summary>Trạng thái & nguyên lý</summary><p>{module?.theory}</p><p>{module?.limit}</p><ProtocolState page={page} state={display} /></details>}
        <p className="settings-note">Reset xóa dữ liệu lab, kể cả PREPARED. Đây là thao tác quản trị.</p>
      </div></>}
    </Modal>}
  </div>
}

function NodeInspector({ id, lab }: { id: string; lab: ReturnType<typeof useLab> }) {
  const process = id === 'gateway' && lab.state.runtime ? { ...lab.state.runtime.gateway, alive: true } : lab.state.services[id]
  const node = lab.state.nodes[id]
  return <><h2>{id === 'web' ? 'Web Client' : id === 'coordinator' ? 'Coordinator / Client' : `Node ${id}`}</h2>
    <div className="inspector-summary"><span>PROCESS ID<strong>{process?.pid ?? '—'}</strong></span><span>Trạng thái<strong>{process?.alive ? 'ONLINE' : id === 'web' ? 'BROWSER' : lab.state.runtime ? 'UNREACHABLE' : 'CRASHED'}</strong></span><span>Giao thức<strong>{node?.transactions?.[0]?.state || (node?.available ? 'AVAILABLE' : '—')}</strong></span></div>
    {id !== 'web' && !lab.state.runtime && <div className="modal-process-controls"><button className="button danger" disabled={lab.busy || !process?.alive} onClick={() => void lab.act(`/process/${id}/crash`)}>Crash tiến trình</button><button className="button secondary" disabled={lab.busy} onClick={() => void lab.act(`/process/${id}/restart`)}>Restart</button>{id !== 'coordinator' && <button className="button secondary" disabled={lab.busy || !process?.alive} onClick={() => void lab.act(`/process/${id}/${node?.available ? 'unavailable' : 'available'}`)}>{node?.available ? 'Đặt unavailable' : 'Cho phép yêu cầu'}</button>}</div>}
    {lab.state.runtime && <p className="muted">Docker lifecycle: scripts/kv-demo.ps1. Dashboard has no Docker socket.</p>}
    <pre>{JSON.stringify(id === 'web' ? { connected: lab.connected, protocol: 'SSE' } : { process, ...(node || {}), ...(id === 'coordinator' ? { transactions: lab.state.transactions, run: lab.state.run } : {}) }, null, 2)}</pre>
  </>
}
