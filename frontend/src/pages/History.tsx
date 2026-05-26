import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listReports } from "../api/client";

export default function History() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listReports().then(setRows).finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <h1 className="text-xl font-semibold mb-3">Past reports</h1>
      {loading && <div className="text-slate-500">Loading…</div>}
      {!loading && rows.length === 0 && (
        <div className="text-slate-500 text-sm">No reports yet. Start one from the home page.</div>
      )}
      <div className="space-y-2">
        {rows.map((r) => (
          <Link
            key={r.id}
            to={`/report/${r.id}`}
            className="block border rounded-lg px-4 py-3 hover:bg-slate-50 flex items-baseline gap-3"
          >
            <span className="font-medium">{r.product}</span>
            <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">{r.market.toUpperCase()}</span>
            <span className="text-xs text-slate-500 ml-auto">
              {new Date(r.generated_at).toLocaleString()}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
