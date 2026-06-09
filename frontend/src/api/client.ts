// 对后端 REST + SSE API 的轻量客户端。
// 所有路径都经由 Vite 代理（见 vite.config.ts），因此可以使用相对 URL。

export interface MarketInfo {
  code: string;
  display_name: string;
  locale: string;
  currency: string;
  flag: string;
}

export interface StartResponse {
  run_id: string;
  market: string;
  locale: string;
  product: string;
}

export interface DagNode {
  id: string;
  label_zh: string;
  label_en: string;
  agent: string;
  description_zh: string;
  description_en: string;
}
export interface DagEdge { src: string; dst: string; condition?: string; }
export interface DagDef { nodes: DagNode[]; edges: DagEdge[]; }

export interface TraceEvent {
  id: string;
  run_id: string;
  agent: string;
  intent: string;
  started_at: string;
  ended_at?: string;
  duration_ms: number;
  status: string;
  prompt_system?: string;
  prompt_user?: string;
  response?: string;
  decision?: string;
  extras?: Record<string, any>;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  model?: string;
}

export interface HealthInfo {
  status: string;
  version: string;
  mock_mode: boolean;
  search_provider: string;
}

export async function getHealth(): Promise<HealthInfo> {
  const r = await fetch("/api/health");
  return r.json();
}

export async function getMarkets(): Promise<MarketInfo[]> {
  const r = await fetch("/api/analysis/markets");
  const j = await r.json();
  return j.markets;
}

export async function getDag(): Promise<DagDef> {
  const r = await fetch("/api/analysis/dag");
  return r.json();
}

export async function startAnalysis(payload: {
  product: string;
  market: string;
  extra_competitors?: string[];
}): Promise<StartResponse> {
  const r = await fetch("/api/analysis/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`start failed: ${r.status}`);
  return r.json();
}

export interface StreamHandlers {
  onTrace: (ev: TraceEvent) => void;
  onDone: (info: { run_id: string; report_id: string | null; error: string | null }) => void;
  onError?: (err: any) => void;
}

export function streamRun(runId: string, h: StreamHandlers): () => void {
  const es = new EventSource(`/api/analysis/stream/${runId}`);
  es.addEventListener("trace", (e) => {
    try { h.onTrace(JSON.parse((e as MessageEvent).data)); }
    catch (err) { h.onError?.(err); }
  });
  es.addEventListener("done", (e) => {
    try { h.onDone(JSON.parse((e as MessageEvent).data)); }
    catch (err) { h.onError?.(err); }
    es.close();
  });
  es.onerror = (err) => { h.onError?.(err); };
  return () => es.close();
}

export async function getReport(reportId: string): Promise<any> {
  const r = await fetch(`/api/reports/${reportId}`);
  if (!r.ok) throw new Error("report not found");
  return r.json();
}

export async function listReports(): Promise<any[]> {
  const r = await fetch(`/api/reports/`);
  const j = await r.json();
  return j.reports;
}

export async function deleteReport(reportId: string): Promise<void> {
  const r = await fetch(`/api/reports/${reportId}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete failed: ${r.status}`);
}

export async function getTrace(runId: string): Promise<TraceEvent[]> {
  const r = await fetch(`/api/traces/${runId}`);
  if (!r.ok) return []; // 404 = 该运行没有记录追踪
  const j = await r.json();
  return j.events ?? [];
}

// ---------------------------------------------------------------------------
// 人在回路编辑
// ---------------------------------------------------------------------------
export interface ReportEdit {
  target_path: string;
  value: any;
  note?: string;
}

export async function patchReport(
  reportId: string,
  edits: ReportEdit[],
): Promise<{ ok: boolean; manual_correction_rate: number; report: any }> {
  const r = await fetch(`/api/reports/${reportId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edits }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail || `patch failed: ${r.status}`);
  }
  return r.json();
}

// ---------------------------------------------------------------------------
// 知识演化（跨运行 diff）
// ---------------------------------------------------------------------------
export interface KnowledgeChange {
  path: string;
  change: "added" | "removed" | "changed";
  before?: string | null;
  after?: string | null;
}
export interface KnowledgeDiff {
  entity_key: string;
  name: string;
  market: string;
  from_run_id: string;
  to_run_id: string;
  from_captured_at?: string | null;
  to_captured_at?: string | null;
  changes: KnowledgeChange[];
  summary: string;
}

export async function getKnowledgeDiff(market: string, name: string): Promise<KnowledgeDiff | null> {
  const r = await fetch(`/api/knowledge/diff?market=${encodeURIComponent(market)}&name=${encodeURIComponent(name)}`);
  if (!r.ok) return null;
  return r.json();
}

// ---------------------------------------------------------------------------
// 智能体自评（meta）
// ---------------------------------------------------------------------------
export interface SchemaSuggestion {
  field: string;
  action: string;
  rationale: string;
  evidence: Record<string, number>;
  confidence: number;
}
export interface MetaReport {
  n_reports: number;
  n_competitors: number;
  field_completeness: Record<string, number>;
  top_correction_paths: { path: string; count: number }[];
  top_conflict_paths: { path: string; count: number }[];
  suggestions: SchemaSuggestion[];
}

export async function getMetaSuggestions(): Promise<MetaReport> {
  const r = await fetch(`/api/meta/suggestions`);
  return r.json();
}

// ---------------------------------------------------------------------------
// 恢复一次被中断的运行
// ---------------------------------------------------------------------------
export async function resumeRun(runId: string): Promise<StartResponse> {
  const r = await fetch(`/api/analysis/resume/${runId}`, { method: "POST" });
  if (!r.ok) throw new Error(`resume failed: ${r.status}`);
  return r.json();
}
