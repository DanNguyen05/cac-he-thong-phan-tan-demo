import type { Snapshot } from './types'

export function runControls(state: Snapshot) {
  const status = state.run?.status || ''
  const running = ['RUNNING', 'WAITING'].includes(status)
  const prepared = !!state.runtime && Object.values(state.nodes).some(node =>
    !!node.locks?.length || node.transactions?.some(tx => tx.state === 'PREPARED'))
  // A stopped RPC/group/recovery workflow is not an in-doubt transaction.
  // Preserve the conservative recovery path for commit and legacy runs.
  const unresolved = ['BLOCKED', 'DECISION_PENDING'].includes(status) ||
    (status === 'INTERRUPTED' && (!state.runtime || state.run?.module === 'commit' || prepared))
  const externalWait = running && !!state.runtime &&
    ['AWAIT_CONTAINER_RESTART', 'AWAIT_RPC_STOP', 'AWAIT_RECEIVER_STOP'].includes(String(state.run?.result?.stage))
  return { running, unresolved, externalWait, restartable: status === 'INTERRUPTED' && !unresolved }
}
