import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import '@xyflow/react/dist/style.css'
import { ReactFlow, Controls, Handle, Position, MarkerType, applyNodeChanges, BaseEdge, getSmoothStepPath } from '@xyflow/react'
import type { Edge, EdgeProps, Node, NodeProps, NodeChange, ReactFlowInstance } from '@xyflow/react'
import { Database, Laptop, Layers, Monitor, Server, Workflow } from 'lucide-react'
import type { Page, Snapshot } from './types'
import { tone } from './types'
import { eventLabel, serviceData, useFreshEvents } from './topology'

type ServiceData = ReturnType<typeof serviceData>[number] & Record<string, unknown>
type ServiceNode = Node<ServiceData, 'service'>
type Message = Edge<{ label: string; active: boolean; seq: number; color: string; rpc?: boolean; reverse?: boolean; pending?: boolean }, 'message'>

function Service({ data, selected }: NodeProps<ServiceNode>) {
  const rpc = data.page === 'rpc'
  const Icon = data.id === 'checkpoint' ? Database : data.id === 'log' ? Layers : data.id === 'web' ? Monitor : data.id === 'coordinator' ? rpc ? Laptop : Workflow : Server
  return <div className={`service-node ${data.id === 'coordinator' || data.id === 'web' ? 'client-node' : 'server-node'} ${tone(data.status)} ${selected ? 'selected' : ''}`}>
    <Handle id="in-top" type="target" position={Position.Top} isConnectable={false} />
    <Handle id="out-top" type="source" position={Position.Top} isConnectable={false} />
    <Handle id="in-bottom" type="target" position={Position.Bottom} isConnectable={false} />
    <Handle id="out-left" type="source" position={Position.Left} style={{ top: '72%' }} isConnectable={false} />
    <Handle id="in-left" type="target" position={Position.Left} style={{ top: '30%' }} isConnectable={false} />
    <Handle id="out-right" type="source" position={Position.Right} style={{ top: '30%' }} isConnectable={false} />
    <Handle id="in-right" type="target" position={Position.Right} style={{ top: '72%' }} isConnectable={false} />
    <span className="node-icon"><Icon size={48} strokeWidth={1.8} /></span>
    <strong>{data.title}</strong>
    <span className={`node-status ${['ONLINE', 'DELIVERED', 'DURABLE'].includes(data.status) ? 'green' : tone(data.status)}`}>{data.status}</span>
    {data.value && <span className="node-value" data-testid={rpc && data.id === 'A' ? 'rpc-executions' : undefined}>{data.value}</span>}
    <Handle id="out-bottom" type="source" position={Position.Bottom} isConnectable={false} />
  </div>
}
function MessageEdge(props: EdgeProps<Message>) {
  const data = props.data!
  let [path, x, y] = getSmoothStepPath(props)
  if (data.rpc) {
    const middleX = (props.sourceX + props.targetX) / 2
    const curve = data.reverse ? 70 : -70
    path = `M${props.sourceX},${props.sourceY} Q${middleX},${(props.sourceY + props.targetY) / 2 + curve} ${props.targetX},${props.targetY}`
    x = middleX
    y = (props.sourceY + props.targetY) / 2 + curve / 2 + (data.reverse ? 36 : -36)
  }
  if (!data.rpc && !['checkpoint', 'log'].includes(props.target) && (data.reverse ? props.sourceY > props.targetY : props.targetY > props.sourceY)) x = data.reverse ? props.sourceX : props.targetX
  const width = data.rpc ? 260 : ['checkpoint', 'log'].includes(props.target) ? 80 : 170
  return <>
    <BaseEdge path={path} markerEnd={props.markerEnd} style={{ stroke: data.color, strokeWidth: data.pending ? 2 : 3, strokeDasharray: data.pending ? '7 6' : undefined, opacity: data.pending ? .5 : 1 }} />
    <g className="message-label" transform={`translate(${x},${y})`}><rect x={-width / 2} y={-22} width={width} height={44} rx={22} /><text textAnchor="middle" dy="6" fill={data.color}>{data.label}</text></g>
    {data.active && <circle key={data.seq} className="message-pulse" r={6} fill={data.color}><animateMotion dur="0.8s" repeatCount="1" path={path} /></circle>}
  </>
}
const nodeTypes = { service: memo(Service) }
const edgeTypes = { message: memo(MessageEdge) }
const fitOptions = { padding: .1 }
const proOptions = { hideAttribution: true }

function createNodes(definitions: ServiceData[], compact: boolean): ServiceNode[] {
  return definitions.map((data, index) => ({ id: data.id, type: 'service', data, width: 220,
    position: compact ? { x: 0, y: index * 260 } : { x: data.x, y: data.y }, ariaLabel: `Kiểm tra ${data.title}` }))
}

export default function ReactFlowDiagram({ page, state, onInspect, active = true }: { page: Page; state: Snapshot; onInspect: (id: string) => void; active?: boolean }) {
  const container = useRef<HTMLDivElement>(null)
  const flow = useRef<ReactFlowInstance<ServiceNode, Message> | null>(null)
  const [compact, setCompact] = useState(() => window.innerWidth < 500)
  const fresh = useFreshEvents(state, active)
  const definitions = useMemo(() => serviceData(page, state), [page, state])
  const [nodes, setNodes] = useState<ServiceNode[]>(() => createNodes(definitions, compact))
  const layoutMode = useRef(compact)
  const dimensions = useRef({ width: 0, height: 0 })
  useEffect(() => {
    if (!active) return
    let frame = 0
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      const previous = dimensions.current
      if (!width || !height || (width === previous.width && height === previous.height)) return
      dimensions.current = { width, height }
      setCompact(width < 470)
      if (!previous.width) return // Initial fitView already measures the new graph.
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => { void flow.current?.fitView({ padding: .1, duration: 0 }) })
    })
    if (container.current) observer.observe(container.current)
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [page, active])
  useEffect(() => {
    const changedLayout = layoutMode.current !== compact
    layoutMode.current = compact
    setNodes(previous => {
      const updated = createNodes(definitions, compact).map(node => {
        const old = previous.find(item => item.id === node.id)
        if (!old) return node
        const sameData = Object.keys(node.data).every(key => old.data[key] === node.data[key])
        if (!changedLayout && sameData) return old
        return { ...old, data: sameData ? old.data : node.data, position: changedLayout ? node.position : old.position }
      })
      return updated.length === previous.length && updated.every((node, index) => node === previous[index]) ? previous : updated
    })
  }, [definitions, compact])
  const initialize = useCallback((instance: ReactFlowInstance<ServiceNode, Message>) => { flow.current = instance }, [])
  const changeNodes = useCallback((changes: NodeChange<ServiceNode>[]) => setNodes(current => applyNodeChanges(changes, current)), [])
  const inspect = useCallback((_: unknown, node: ServiceNode) => onInspect(node.id), [onInspect])
  const edge = (id: string, source: string, target: string, label: string, color: string, seq: number, reverse = false, rpc = false): Message => ({
    id, source, target, type: 'message',
    sourceHandle: !compact && ['checkpoint', 'log'].includes(target) ? 'out-right' : rpc && !compact ? reverse ? 'out-left' : 'out-right' : reverse ? 'out-top' : 'out-bottom',
    targetHandle: !compact && ['checkpoint', 'log'].includes(target) ? 'in-left' : rpc && !compact ? reverse ? 'in-right' : 'in-left' : reverse ? 'in-bottom' : 'in-top',
    data: { label, color, seq, reverse, rpc: rpc && !compact, pending: seq === 0, active: fresh.includes(seq) },
    markerEnd: { type: MarkerType.ArrowClosed, color, width: 17, height: 17 },
  })
  let edges: Message[]
  if (page === 'rpc') {
    const request = [...state.events].reverse().find(e => ['SEND', 'RETRY', 'TIMEOUT', 'REQUEST_LOST', 'UNAVAILABLE'].includes(e.kind) && (e.source === 'Client' || e.target === 'A'))
    const response = [...state.events].reverse().find(e => ['ACK', 'RESPONSE_LOST'].includes(e.kind) && ['A', 'rpc'].includes(e.source))
    const requestLabel = !request ? 'Yêu cầu' : request.kind === 'SEND' ? `Request · ${String(request.data.operation_id || '').slice(-8)}` : request.kind === 'RETRY' ? 'Retry · cùng request ID' : request.kind === 'REQUEST_LOST' ? 'Mất yêu cầu' : request.kind === 'TIMEOUT' ? 'Timeout' : 'Server không khả dụng'
    const responseLabel = !response ? 'Chờ phản hồi' : response.kind === 'ACK' ? 'Response · OK' : 'Mất phản hồi'
    edges = [
      edge('rpc-request', 'coordinator', 'A', requestLabel, request && /TIMEOUT|LOST|UNAVAILABLE/.test(request.kind) ? 'var(--red)' : 'var(--blue)', request?.seq || 0, false, true),
      edge('rpc-response', 'A', 'coordinator', responseLabel, response?.kind === 'RESPONSE_LOST' ? 'var(--red)' : 'var(--green)', response?.seq || 0, true, true),
    ]
  } else {
    edges = definitions.filter(node => !['coordinator', 'checkpoint', 'log'].includes(node.id)).map(node => {
      const event = [...state.events].reverse().find(e => (e.source === node.id || e.target === node.id) && ['SEND', 'ACK', 'TIMEOUT', 'RETRY', 'REQUEST_LOST', 'RESPONSE_LOST', 'VOTE', 'UNAVAILABLE', 'RETRANSMIT'].includes(e.kind))
      const reverse = event?.source === node.id
      return edge(`link-${node.id}`, node.id === 'rpc' && state.runtime ? reverse ? 'rpc' : 'web' : node.id === 'web' ? 'web' : reverse ? node.id : 'coordinator', node.id === 'rpc' && state.runtime ? reverse ? 'web' : 'rpc' : node.id === 'web' ? 'coordinator' : reverse ? 'coordinator' : node.id,
        node.id === 'web' ? state.runtime ? 'HTTP' : 'SSE' : event ? eventLabel(event, state) : 'HTTP',
        event && /LOST|TIMEOUT|UNAVAILABLE|NO/.test(event.kind + event.data.vote) ? 'var(--red)' : reverse ? 'var(--green)' : 'var(--blue)', event?.seq || 0, !!reverse)
    })
    if (page === 'recovery') {
      for (const [id, kind] of [['checkpoint', 'CHECKPOINT'], ['log', 'RECOVERY']]) {
        const event = [...state.events].reverse().find(e => e.kind === kind)
        edges.push(edge(`A-${id}`, 'A', id, event ? `#${event.seq}` : '—', 'var(--blue)', event?.seq || 0))
      }
    }
  }
  return <div ref={container} className={`diagram ${page === 'overview' ? 'overview-diagram' : ''}`} data-renderer="reactflow">
    <ReactFlow id={`topology-${page}`} onInit={initialize} key={String(compact)} nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      onNodesChange={changeNodes}
      onNodeClick={inspect} fitView fitViewOptions={fitOptions}
      minZoom={.25} maxZoom={1.6} colorMode="light" nodesConnectable={false} edgesReconnectable={false}
      deleteKeyCode={null} proOptions={proOptions}>
      <Controls showInteractive={false} />
    </ReactFlow>
  </div>
}
