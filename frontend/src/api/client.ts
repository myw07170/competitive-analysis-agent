// Thin client over the backend REST + SSE API.
// All paths are proxied through Vite (see vite.config.ts) so we can use relative URLs.

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

export async function getTrace(runId: string): Promise<TraceEvent[]> {
  const r = await fetch(`/api/traces/${runId}`);
  const j = await r.json();
  return j.events;
}
