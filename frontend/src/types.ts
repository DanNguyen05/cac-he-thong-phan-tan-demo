export type Module = 'rpc' | 'group' | 'commit' | 'recovery'
export type Page = 'overview' | Module
export type LogEvent = { seq: number; time: number; run_id: string; source: string; target: string; kind: string; detail: string; data: Record<string, unknown> }
export type NodeState = {
  kv?: Record<string, number | string>; boot_id?: string;
  locks?: { key: string; tx_id: string }[];
  group?: { stream: string; seq: number; payload: string; delivered: number }[];
  node: string; pid?: number; available: boolean; crashed?: boolean; unreachable?: boolean;
  counters?: Record<string, number>; memory_value?: number;
  multicast?: { id: string; payload: string }[];
  transactions?: { id: string; state: string; amount?: number; run_id?: string }[];
  checkpoint?: { seq: number; value: number };
  operations?: { seq: number; id: string; delta: number }[];
  recovery?: { checkpoint_seq?: number; checkpoint_value?: number; replayed?: string[]; value?: number };
  logs?: { seq: number; kind: string; id: string; data: string }[];
}
export type Run = { id: string; module: Module; scenario: string; status: string; config: Record<string, unknown>; result: Record<string, unknown> | null; created: number }
export type Snapshot = {
  runtime?: { mode: 'kv'; containerized: boolean; services: number; name: string; gateway: { pid: number; boot_id: string; available: boolean } };
  run: Run | null; events: LogEvent[]; nodes: Record<string, NodeState>;
  services: Record<string, { alive: boolean; pid: number; port: number; boot_id?: string; observed_at?: number }>;
  transactions: { id: string; state: string; votes: Record<string, string>; acknowledgments: Record<string, unknown> }[];
}
export type Catalog = Record<Module, [string, string, string][]>
export const EMPTY: Snapshot = { run: null, events: [], nodes: {}, services: {}, transactions: [] }
export const statusNames: Record<string, string> = {
  RUNNING: 'Đang thực thi', WAITING: 'Chờ bước tiếp theo', COMPLETED: 'Hoàn tất',
  FAILED: 'Thất bại', PARTIAL: 'Nhận một phần', BLOCKED: 'Đang blocking',
  DECISION_PENDING: 'Chờ gửi quyết định', INTERRUPTED: 'Bị gián đoạn',
  PREPARED: 'PREPARED', COMMIT: 'COMMIT', ABORT: 'ABORT', PREPARING: 'PREPARING',
}
export function tone(value: string) {
  if (/FAIL|ABORT|CRASH|UNAVAILABLE|UNREACHABLE|HEALTH_DOWN|LOST|ERROR|INTERRUPTED/.test(value)) return 'red'
  if (/WAIT|PREPAR|BLOCK|TIMEOUT|PARTIAL|PENDING|RETRY|DELAY|NACK/.test(value)) return 'amber'
  if (/COMPLET|COMMIT|ACK|RECOVERY|CHECKPOINT|SUPPRESSED|AVAILABLE|IDEMPOTENCE/.test(value)) return 'green'
  return 'blue'
}
