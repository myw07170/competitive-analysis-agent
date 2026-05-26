import { useMemo } from "react";

export interface ComparisonCell {
  competitor: string;
  value: string;
  detail?: string | null;
}

export interface ComparisonRow {
  label: string;
  category?: string | null;
  cells: ComparisonCell[];
}

export interface ComparisonMatrix {
  competitors: string[];
  feature_rows: ComparisonRow[];
  pricing_rows: ComparisonRow[];
  user_rows: ComparisonRow[];
  keywords: Record<string, string[]>;
  function_coverage: Record<string, number>;
  source_counts: Record<string, number>;
  pricing_floor: Record<string, number | null>;
}

interface Props {
  t: (k: string) => string;
  comparison?: ComparisonMatrix | null;
}

const PALETTE = ["#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed", "#0891b2"];

export default function ComparisonView({ t, comparison }: Props) {
  if (!comparison || !comparison.competitors?.length) {
    return <div className="text-sm text-slate-400">{t("comparison.empty")}</div>;
  }

  const { competitors } = comparison;
  const colorFor = useMemo(() => {
    const map: Record<string, string> = {};
    competitors.forEach((n, i) => (map[n] = PALETTE[i % PALETTE.length]));
    return map;
  }, [competitors]);

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-sm font-semibold mb-3 text-slate-700">{t("comparison.charts")}</h3>
        <div className="grid md:grid-cols-3 gap-4">
          <BarChart
            title={t("comparison.coverage")}
            unit=""
            data={competitors.map((n) => ({
              name: n,
              value: comparison.function_coverage[n] ?? 0,
              color: colorFor[n],
            }))}
          />
          <BarChart
            title={t("comparison.sources")}
            unit=""
            data={competitors.map((n) => ({
              name: n,
              value: comparison.source_counts[n] ?? 0,
              color: colorFor[n],
            }))}
          />
          <BarChart
            title={t("comparison.entry_price")}
            unit=""
            data={competitors.map((n) => ({
              name: n,
              value: comparison.pricing_floor[n] ?? 0,
              color: colorFor[n],
              missing: comparison.pricing_floor[n] == null,
            }))}
          />
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold mb-3 text-slate-700">{t("comparison.keywords")}</h3>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          {competitors.map((n) => (
            <KeywordCard
              key={n}
              name={n}
              color={colorFor[n]}
              keywords={comparison.keywords[n] || []}
            />
          ))}
        </div>
      </section>

      <ComparisonTable
        title={t("comparison.feature")}
        rows={comparison.feature_rows}
        competitors={competitors}
        colorFor={colorFor}
      />
      <ComparisonTable
        title={t("comparison.pricing")}
        rows={comparison.pricing_rows}
        competitors={competitors}
        colorFor={colorFor}
      />
      <ComparisonTable
        title={t("comparison.user")}
        rows={comparison.user_rows}
        competitors={competitors}
        colorFor={colorFor}
      />
    </div>
  );
}

function BarChart({
  title,
  data,
  unit,
}: {
  title: string;
  unit: string;
  data: { name: string; value: number; color: string; missing?: boolean }[];
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="border rounded-lg p-3">
      <div className="text-xs font-medium text-slate-600 mb-2">{title}</div>
      <div className="space-y-1.5">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-2 text-xs">
            <span className="w-20 truncate text-slate-700" title={d.name}>{d.name}</span>
            <div className="flex-1 bg-slate-100 rounded h-3 relative overflow-hidden">
              <div
                className="h-3 rounded transition-all"
                style={{
                  width: d.missing ? "4%" : `${Math.max(2, (d.value / max) * 100)}%`,
                  background: d.missing ? "#cbd5e1" : d.color,
                }}
              />
            </div>
            <span className="w-12 text-right text-slate-600 tabular-nums">
              {d.missing ? "—" : `${d.value}${unit}`}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function KeywordCard({
  name,
  color,
  keywords,
}: {
  name: string;
  color: string;
  keywords: string[];
}) {
  return (
    <div className="border rounded-lg p-3" style={{ borderLeft: `4px solid ${color}` }}>
      <div className="text-sm font-semibold text-slate-800 mb-2">{name}</div>
      <div className="flex flex-wrap gap-1.5">
        {keywords.length === 0 && <span className="text-xs text-slate-400">—</span>}
        {keywords.map((k, i) => (
          <span
            key={i}
            className="text-[11px] px-2 py-0.5 rounded-full"
            style={{ background: `${color}1a`, color }}
          >
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}

function ComparisonTable({
  title,
  rows,
  competitors,
  colorFor,
}: {
  title: string;
  rows: ComparisonRow[];
  competitors: string[];
  colorFor: Record<string, string>;
}) {
  if (!rows || rows.length === 0) return null;
  return (
    <section>
      <h3 className="text-sm font-semibold mb-3 text-slate-700">{title}</h3>
      <div className="overflow-x-auto border rounded-lg">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-3 py-2 font-medium text-slate-600 w-1/4">—</th>
              {competitors.map((n) => (
                <th key={n} className="text-left px-3 py-2 font-medium text-slate-700">
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle"
                    style={{ background: colorFor[n] }}
                  />
                  {n}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50/50"}>
                <td className="px-3 py-2 font-medium text-slate-700">{row.label}</td>
                {competitors.map((n) => {
                  const cell = row.cells.find((c) => c.competitor === n);
                  return (
                    <td key={n} className="px-3 py-2 text-slate-700 align-top">
                      {cell?.value || "—"}
                      {cell?.detail && (
                        <div className="text-[11px] text-slate-400">{cell.detail}</div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
