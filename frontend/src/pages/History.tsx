import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { deleteReport, listReports } from "../api/client";
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
