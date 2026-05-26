import { Link, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Report from "./pages/Report";
import History from "./pages/History";
import { useEffect, useState } from "react";
import { getHealth, HealthInfo } from "./api/client";

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  useEffect(() => { getHealth().then(setHealth).catch(() => {}); }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-white">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-2xl">🎯</span>
            <span className="font-semibold text-lg">Competitive Analysis Agent</span>
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link to="/" className="text-slate-600 hover:text-brand-600">New</Link>
            <Link to="/history" className="text-slate-600 hover:text-brand-600">History</Link>
            {health && (
              <span className={"text-xs px-2 py-1 rounded " +
                (health.mock_mode ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800")}>
                {health.mock_mode ? "mock mode" : `model: ok`}
              </span>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/report/:reportId" element={<Report />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </main>

      <footer className="border-t bg-white py-3 text-center text-xs text-slate-500">
        Multi-agent system · Volcengine Ark LLM · LangGraph DAG · Source-traceable output
      </footer>
    </div>
  );
}
