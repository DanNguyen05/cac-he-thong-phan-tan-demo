import { Component } from 'react'
import type { ReactNode } from 'react'
import Primary from '@lab/topology'
import Offline from './OfflineDiagram'
import type { Page, Snapshot } from './types'

class RendererBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}
export default function Diagram({ renderer, ...props }: { page: Page; state: Snapshot; onInspect: (id: string) => void; renderer?: 'reactflow' | 'svg' }) {
  return <div className="topology-canvas"><RendererBoundary key={`${props.page}-${renderer}`} fallback={<Offline {...props} />}>
    {renderer === 'svg' ? <Offline key={props.page} {...props} /> : <Primary key={props.page} {...props} />}
  </RendererBoundary></div>
}
