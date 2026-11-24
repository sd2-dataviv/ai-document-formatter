import { FileText, LayoutTemplate, Monitor, Moon, Plus, Search, Sun, Trash2, Wand2 } from "lucide-react";
import type { ThemePref } from "../theme";
import type { DocStatus, DocumentSummary, Health } from "../types";

export type View = "workspace" | "templates";

interface Props {
  view: View;
  onView: (v: View) => void;
  documents: DocumentSummary[];
  activeId: number | null;
  search: string;
  onSearch: (q: string) => void;
  onOpen: (id: number) => void;
  onDelete: (id: number) => void;
  onNew: () => void;
  health: Health | null;
  theme: ThemePref;
  onTheme: (t: ThemePref) => void;
}

const STATUS_DOT: Record<DocStatus, string> = {
  completed: "bg-emerald-500",
  failed: "bg-rose-500",
  cancelled: "bg-slate-300 dark:bg-slate-600",
  queued: "bg-amber-400 animate-pulse",
  processing: "bg-indigo-500 animate-pulse",
};

const THEMES = [
  { key: "light", label: "Light", Icon: Sun },
  { key: "system", label: "System", Icon: Monitor },
  { key: "dark", label: "Dark", Icon: Moon },
] as const;

function relativeTime(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function Sidebar(p: Props) {
  const llmOk = p.health?.llm.reachable && p.health.llm.model_available;
  const dbOk = p.health?.database;

  return (
    <aside className="surface flex h-full w-72 shrink-0 flex-col border-r border-slate-200 dark:border-slate-800">
      <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
        <div className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
          <Wand2 className="size-5" />
        </div>
        <div>
          <div className="ink-strong text-[15px] leading-tight font-semibold">DocFormatter AI</div>
          <div className="ink-muted text-xs">Local LLM document styling</div>
        </div>
      </div>

      <nav className="flex gap-1 px-3">
        {(
          [
            ["workspace", "Workspace", FileText],
            ["templates", "Templates", LayoutTemplate],
          ] as const
        ).map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => p.onView(key)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
              p.view === key
                ? "selected"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            }`}
          >
            <Icon className="size-4" />
            {label}
          </button>
        ))}
      </nav>

      <div className="px-3 pt-4">
        <button
          onClick={p.onNew}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600"
        >
          <Plus className="size-4" /> New document
        </button>
        <div className="relative mt-3">
          <Search className="ink-faint pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <input
            value={p.search}
            onChange={(e) => p.onSearch(e.target.value)}
            placeholder="Search history…"
            aria-label="Search history"
            className="field py-2 pr-3 pl-9"
          />
        </div>
      </div>

      <div className="ink-faint mt-3 px-5 text-[11px] font-semibold tracking-wider uppercase">History</div>
      <div className="mt-1 flex-1 overflow-y-auto px-2 pb-2">
        {p.documents.length === 0 && (
          <div className="ink-faint px-3 py-8 text-center text-sm">
            {p.search ? "No matching documents" : "Formatted documents will appear here"}
          </div>
        )}
        {p.documents.map((d) => (
          <div
            key={d.id}
            onClick={() => p.onOpen(d.id)}
            className={`group relative mb-0.5 cursor-pointer rounded-lg px-3 py-2.5 transition ${
              d.id === p.activeId
                ? "bg-indigo-50 ring-1 ring-indigo-200 dark:bg-indigo-500/10 dark:ring-indigo-500/30"
                : "hover-row"
            }`}
          >
            <div className="flex items-start gap-2">
              <span title={d.status} className={`mt-1.5 size-1.5 shrink-0 rounded-full ${STATUS_DOT[d.status]}`} />
              <div className="min-w-0 flex-1">
                <div className="truncate pr-6 text-sm font-medium text-slate-800 dark:text-slate-200">{d.title}</div>
                <div className="ink-muted mt-0.5 flex items-center gap-1.5 text-xs">
                  <span className="truncate">{d.template_name ?? "Custom"}</span>
                  <span>·</span>
                  <span className="shrink-0">{relativeTime(d.updated_at)}</span>
                </div>
              </div>
            </div>
            <button
              title="Delete"
              aria-label={`Delete ${d.title}`}
              onClick={(e) => {
                e.stopPropagation();
                p.onDelete(d.id);
              }}
              className="ink-faint absolute top-2.5 right-2 hidden rounded p-1 group-hover:block hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/15 dark:hover:text-rose-400"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>

      <div className="space-y-2.5 border-t border-slate-200 px-5 py-3 text-xs dark:border-slate-800">
        <div className="flex items-center justify-between">
          <span className="ink-muted font-medium">Theme</span>
          <div className="segmented" role="radiogroup" aria-label="Color theme">
            {THEMES.map(({ key, label, Icon }) => (
              <button
                key={key}
                role="radio"
                aria-checked={p.theme === key}
                title={label}
                onClick={() => p.onTheme(key)}
                className={`rounded-md px-2 py-1 transition ${p.theme === key ? "seg-on" : "seg-off"}`}
              >
                <Icon className="size-3.5" />
              </button>
            ))}
          </div>
        </div>
        <StatusRow
          ok={!!llmOk}
          loading={!p.health}
          label={p.health ? p.health.llm.model : "Checking LLM…"}
          detail={
            p.health
              ? !p.health.llm.reachable
                ? "Ollama unreachable"
                : !p.health.llm.model_available
                  ? "Model not pulled"
                  : p.health.llm.url.replace(/^https?:\/\//, "")
              : ""
          }
        />
        <StatusRow ok={!!dbOk} loading={!p.health} label="PostgreSQL" detail={dbOk ? "connected" : "offline"} />
      </div>
    </aside>
  );
}

function StatusRow({ ok, loading, label, detail }: { ok: boolean; loading: boolean; label: string; detail: string }) {
  return (
    <div className="flex items-center gap-2" title={detail}>
      <span
        className={`size-2 rounded-full ${
          loading ? "animate-pulse bg-slate-300 dark:bg-slate-600" : ok ? "bg-emerald-500" : "bg-rose-500"
        }`}
      />
      <span className="ink font-medium">{label}</span>
      <span className="ink-faint ml-auto truncate">{detail}</span>
    </div>
  );
}
