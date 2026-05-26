import { useState } from "react";

interface SourceRef {
  id: string;
  kind: string;
  title: string;
  url?: string | null;
  snippet?: string;
  confidence?: number;
}

interface Props {
  sources: SourceRef[];
  t: (k: string) => string;
  compact?: boolean;
}

const KIND_LABEL: Record<string, string> = {
  web: "source.kind.web",
  doc: "source.kind.doc",
  interview: "source.kind.interview",
  questionnaire: "source.kind.questionnaire",
  llm_prior: "source.kind.llm_prior",
};

export default function SourceBadge({ sources, t, compact = false }: Props) {
  const [open, setOpen] = useState(false);
  if (!sources || sources.length === 0) return null;
  const visible = open ? sources : sources.slice(0, compact ? 1 : 2);
  return (
    <div className="flex flex-wrap gap-1.5 items-center">
      {visible.map((s) => (
        <a
          key={s.id}
          href={s.url || "#"}
          target={s.url ? "_blank" : undefined}
          rel="noreferrer"
          title={s.snippet}
          className="inline-flex items-center gap-1 text-[10px] border rounded px-1.5 py-0.5 bg-slate-50 hover:bg-slate-100"
        >
          <span className="text-slate-500">[{t(KIND_LABEL[s.kind] || s.kind)}]</span>
          <span className="text-slate-700 max-w-[160px] truncate">{s.title || s.url}</span>
          {typeof s.confidence === "number" && (
            <span className="text-slate-400">·{(s.confidence * 100).toFixed(0)}%</span>
          )}
        </a>
      ))}
      {sources.length > visible.length && !open && (
        <button onClick={() => setOpen(true)} className="text-[10px] text-brand-600">
          +{sources.length - visible.length}
        </button>
      )}
    </div>
  );
}
