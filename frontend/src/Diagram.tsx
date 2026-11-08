import { Component, memo, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import Primary from '@lab/topology'
import Offline from './OfflineDiagram'
import type { Page, Snapshot } from './types'
import { sameDiagramSnapshot } from './snapshot'

type Props = { page: Page; state: Snapshot; onInspect: (id: string) => void; renderer?: 'reactflow' | 'svg' }
class RendererBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

const CachedRenderer = memo(function CachedRenderer({ active, renderer, ...props }: Props & { active: boolean }) {
  return <RendererBoundary key={renderer} fallback={<Offline {...props} active={active} />}>
    {renderer === 'svg' ? <Offline {...props} active={active} /> : <Primary {...props} active={active} />}
  </RendererBoundary>
}, (previous, next) => previous.active === next.active && (!next.active || (previous.onInspect === next.onInspect && previous.renderer === next.renderer && sameDiagramSnapshot(previous.state, next.state))))

/** Retain only visited canvases, including their dragged positions and viewport. */
function Diagram({ page, state, onInspect, renderer }: Props) {
  const [visited, setVisited] = useState<Page[]>([page])
  const snapshots = useRef<Partial<Record<Page, Snapshot>>>({})
  const pages = visited.includes(page) ? visited : [...visited, page]
  useLayoutEffect(() => {
    snapshots.current[page] = state
    if (!visited.includes(page)) setVisited(previous => [...previous, page])
  }, [page, state, visited])
  return <div className="topology-canvas">{pages.map(name => <div className="topology-page" data-topology-page={name} key={name} hidden={name !== page} inert={name !== page}>
    <CachedRenderer page={name} state={name === page ? state : snapshots.current[name] || state} active={name === page} renderer={renderer} onInspect={onInspect} />
  </div>)}</div>
}
export default memo(Diagram, (previous, next) => previous.page === next.page && previous.renderer === next.renderer && previous.onInspect === next.onInspect && sameDiagramSnapshot(previous.state, next.state))
