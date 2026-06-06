import { Link, Route, Routes, useLocation } from "react-router-dom";
import Home from "./pages/Home";
import Report from "./pages/Report";
import History from "./pages/History";
import { useEffect, useMemo, useState } from "react";
import { getHealth, HealthInfo } from "./api/client";
import { makeT, marketToLocale } from "./i18n";

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  // The selected target market lives at the top level so the header language
  // can follow it: Chinese by default, switching to English only when the US
  // market is picked on the setup page.
  const [market, setMarket] = useState("cn");
  const t = useMemo(() => makeT(marketToLocale(market)), [market]);

  // On the analysis page ("/") a run may be in progress, so "历史报告" opens a
  // new tab to preserve it; elsewhere (e.g. viewing a saved report) it just
  // navigates the current tab. "新建分析" always opens a new tab.
  const { pathname } = useLocation();
  const historyOpensNewTab = pathname === "/";

  useEffect(() => { getHealth().then(setHealth).catch(() => {}); }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-white">
        <div className="max-w-[var(--page-max-width)] mx-auto px-6 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-2xl">🎯</span>
            <span className="font-semibold text-lg">{t("app.header")}</span>
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            {/* New analysis always opens a new tab so the current run is kept. */}
            <Link to="/" target="_blank" rel="noopener noreferrer" className="text-slate-600 hover:text-brand-600">{t("nav.new")}</Link>
            <Link
              to="/history"
              {...(historyOpensNewTab ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              className="text-slate-600 hover:text-brand-600"
            >{t("nav.history")}</Link>
            {health && (
              <span className={"text-xs px-2 py-1 rounded " +
                (health.mock_mode ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800")}>
                {health.mock_mode ? t("health.mock") : t("health.ok")}
              </span>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home market={market} setMarket={setMarket} />} />
          <Route path="/report/:reportId" element={<Report />} />
          <Route path="/history" element={<History market={market} />} />
        </Routes>
      </main>

      <footer className="border-t bg-white py-3 text-center text-xs text-slate-500">
        Multi-agent system · Volcengine Ark LLM · LangGraph DAG · Source-traceable output
      </footer>
    </div>
  );
}
