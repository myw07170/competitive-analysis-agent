import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MetaReport, deleteReport, getMetaSuggestions, listReports } from "../api/client";
import { makeT, marketToLocale } from "../i18n";

interface HistoryProps {
  // Drives the page language (Chinese by default; English for the US market).
  market: string;
}

export default function History({ market }: HistoryProps) {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  // The row pending deletion — non-null shows the confirm modal.
  const [pendingDelete, setPendingDelete] = useState<any | null>(null);
  const [deleting, setDeleting] = useState(false);

  const t = useMemo(() => makeT(marketToLocale(market)), [market]);

  useEffect(() => {
    listReports().then(setRows).finally(() => setLoading(false));
  }, []);

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteReport(pendingDelete.id);
      setRows((rs) => rs.filter((r) => r.id !== pendingDelete.id));
      setPendingDelete(null);
    } catch {
      alert(t("history.delete_failed"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <h1 className="text-xl font-semibold mb-3">{t("history.title")}</h1>
      <MetaPanel t={t} />
      {loading && <div className="text-slate-500">{t("common.loading")}</div>}
      {!loading && rows.length === 0 && (
        <div className="text-slate-500 text-sm">{t("history.empty")}</div>
      )}
      <div className="space-y-2">
        {rows.map((r) => (
          <div
            key={r.id}
            className="group border rounded-lg px-4 py-3 hover:bg-slate-50 flex items-center gap-3"
          >
            <span className="font-medium">{r.product}</span>
            <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">{r.market.toUpperCase()}</span>
            <span className="text-xs text-slate-500 ml-auto">
              {new Date(r.generated_at).toLocaleString()}
            </span>
            {/* Hover-revealed actions. */}
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
              <Link
                to={`/report/${r.id}`}
                className="text-xs px-2.5 py-1 rounded border border-brand-600 text-brand-700 hover:bg-brand-50"
              >
                {t("common.view")}
              </Link>
              <button
                type="button"
                onClick={() => setPendingDelete(r)}
                className="text-xs px-2.5 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50"
              >
                {t("common.delete")}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Confirm-delete modal. */}
      {pendingDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
          onClick={() => !deleting && setPendingDelete(null)}
        >
          <div
            className="bg-white rounded-xl shadow-lg max-w-sm w-full p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold mb-2">{t("history.confirm_delete.title")}</h2>
            <p className="text-sm text-slate-600 mb-4">
              {t("history.confirm_delete.message", { product: pendingDelete.product })}
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => setPendingDelete(null)}
                className="text-sm px-3 py-1.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-60"
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={confirmDelete}
                className="text-sm px-3 py-1.5 rounded bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-60"
              >
                {deleting ? t("history.deleting") : t("common.confirm")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Agent self-evaluation: field completeness + schema-evolution suggestions. */
function MetaPanel({ t }: { t: (k: string, v?: Record<string, string | number>) => string }) {
  const [meta, setMeta] = useState<MetaReport | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    getMetaSuggestions().then(setMeta).catch(() => {});
  }, []);

  if (!meta || meta.n_competitors === 0) return null;

  const actionLabel = (a: string) => t(`meta.action.${a}`) || a;
  const entries = Object.entries(meta.field_completeness).sort((a, b) => a[1] - b[1]);

  return (
    <div className="border rounded-xl mb-5 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left"
      >
        <span className="font-semibold text-sm">🧭 {t("meta.title")}</span>
        <span className="text-xs text-slate-400">
          {t("meta.reports")}: {meta.n_reports} · {t("meta.competitors")}: {meta.n_competitors} ·{" "}
          {t("meta.suggestions")}: {meta.suggestions.length}
        </span>
        <span className={"ml-auto text-slate-400 transition-transform " + (open ? "rotate-90" : "")}>
          ▸
        </span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-4">
          <p className="text-xs text-slate-500">{t("meta.help")}</p>

          {meta.suggestions.length === 0 && (
            <div className="text-sm text-slate-400">{t("meta.no_suggestions")}</div>
          )}
          {meta.suggestions.length > 0 && (
            <div className="space-y-2">
              {meta.suggestions.map((s, i) => (
                <div key={i} className="border rounded-lg px-3 py-2 flex items-start gap-3">
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 shrink-0 uppercase">
                    {actionLabel(s.action)}
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-mono text-slate-700">{s.field}</div>
                    <div className="text-xs text-slate-500">{s.rationale}</div>
                  </div>
                  <span className="ml-auto text-[11px] text-slate-400 shrink-0">
                    {(s.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}

          <div>
            <div className="text-xs font-medium text-slate-600 mb-1">{t("meta.completeness")}</div>
            <div className="space-y-1">
              {entries.map(([field, frac]) => (
                <div key={field} className="flex items-center gap-2 text-xs">
                  <span className="w-48 shrink-0 font-mono text-slate-500 truncate">{field}</span>
                  <div className="flex-1 h-2 bg-slate-100 rounded overflow-hidden">
                    <div
                      className={
                        "h-2 " +
                        (frac < 0.2 ? "bg-rose-400" : frac < 0.6 ? "bg-amber-400" : "bg-emerald-400")
                      }
                      style={{ width: `${Math.round(frac * 100)}%` }}
                    />
                  </div>
                  <span className="w-10 text-right tabular-nums text-slate-500">
                    {Math.round(frac * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
