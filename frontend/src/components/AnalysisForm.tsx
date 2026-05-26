import { useState } from "react";
import type { MarketInfo } from "../api/client";

interface Props {
  t: (k: string) => string;
  markets: MarketInfo[];
  market: string;
  onMarketChange: (code: string) => void;
  onStart: (product: string, extras: string[]) => void;
  running: boolean;
}

export default function AnalysisForm({ t, markets, market, onMarketChange, onStart, running }: Props) {
  const [product, setProduct] = useState("");
  const [extras, setExtras] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!product.trim()) return;
    const extraList = extras.split(",").map((s) => s.trim()).filter(Boolean);
    onStart(product.trim(), extraList);
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{t("form.product.label")}</label>
        <input
          className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
          placeholder={t("form.product.placeholder")}
          value={product}
          onChange={(e) => setProduct(e.target.value)}
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{t("form.market.label")}</label>
        <div className="grid grid-cols-2 gap-2">
          {markets.map((m) => (
            <button
              type="button"
              key={m.code}
              onClick={() => onMarketChange(m.code)}
              className={
                "border rounded-lg px-3 py-2 text-sm text-left flex items-center gap-2 " +
                (market === m.code
                  ? "border-brand-600 bg-brand-50 text-brand-900"
                  : "border-slate-200 hover:border-slate-300")
              }
            >
              <span className="text-lg">{m.flag}</span>
              <div className="flex flex-col">
                <span className="font-medium">{m.display_name}</span>
                <span className="text-xs text-slate-500">{m.locale} · {m.currency}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">{t("form.extra.label")}</label>
        <input
          className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500"
          placeholder={t("form.extra.placeholder")}
          value={extras}
          onChange={(e) => setExtras(e.target.value)}
        />
      </div>

      <button
        type="submit"
        disabled={running}
        className="w-full bg-brand-600 text-white rounded-lg py-2 font-medium hover:bg-brand-700 disabled:opacity-60"
      >
        {running ? t("form.submit.running") : t("form.submit")}
      </button>
    </form>
  );
}
