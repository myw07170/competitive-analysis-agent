import { Link, Route, Routes, useLocation } from "react-router-dom";
import Home from "./pages/Home";
import Report from "./pages/Report";
import History from "./pages/History";
import { useEffect, useMemo, useState } from "react";
import { getHealth, HealthInfo } from "./api/client";
import { makeT, marketToLocale } from "./i18n";

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  // 选中的目标市场保存在顶层，使顶栏语言能随之变化：默认中文，
  // 仅当在设置页选择美国市场时才切换为英文。
  const [market, setMarket] = useState("cn");
  const t = useMemo(() => makeT(marketToLocale(market)), [market]);

  // 在分析页（"/"）上可能有运行正在进行，因此"历史报告"会打开一个新标签页
  // 以保留它；在其他位置（例如查看已保存的报告）则只在当前标签页内导航。
  // "新建分析"总是打开一个新标签页。
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
            {/* 新建分析总是打开新标签页，以保留当前运行。 */}
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
