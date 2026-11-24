import { Brain, Check, ChevronDown, Clock, Copy, Download, Eye, FileCode2, Loader2, Save, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ExportFormat } from "../types";

type Tab = "preview" | "markdown" | "reasoning";

interface Props {
  markdown: string;
  thinking: string;
  streaming: boolean;
  phase: "idle" | "queued" | "thinking" | "writing";
  queuePosition: number;
  chunk: { index: number; total: number } | null;
  elapsedMs: number;
  durationMs: number | null;
  docId: number | null;
  dirty: boolean;
  saving: boolean;
  onEdit: (md: string) => void;
  onSave: () => void;
  onExport: (f: ExportFormat) => Promise<void>;
}

const EXPORTS: { key: ExportFormat; label: string; hint: string }[] = [
  { key: "docx", label: "Word (.docx)", hint: "Editable in Word / Google Docs" },
  { key: "pdf", label: "PDF (.pdf)", hint: "Print-ready A4" },
  { key: "html", label: "HTML (.html)", hint: "Styled standalone page" },
  { key: "md", label: "Markdown (.md)", hint: "Plain text source" },
];

// Typography for the rendered document, in both themes.
const PROSE = [
  "doc-prose prose prose-slate dark:prose-invert mx-auto max-w-3xl px-8 py-8",
  "prose-headings:scroll-mt-4",
  "prose-h1:text-3xl prose-h1:border-b prose-h1:border-slate-200 prose-h1:pb-3 dark:prose-h1:border-slate-700",
  "prose-h2:border-b prose-h2:border-slate-100 prose-h2:pb-1.5 dark:prose-h2:border-slate-800",
  "prose-a:text-indigo-600 dark:prose-a:text-indigo-400",
  "prose-code:before:content-none prose-code:after:content-none prose-code:rounded prose-code:px-1 prose-code:py-0.5 prose-code:font-normal",
  "prose-code:bg-slate-100 dark:prose-code:bg-slate-800",
  "prose-pre:bg-slate-900 dark:prose-pre:bg-slate-950 dark:prose-pre:ring-1 dark:prose-pre:ring-slate-800",
  "prose-th:bg-slate-50 dark:prose-th:bg-slate-800/60",
  "prose-blockquote:border-indigo-400 prose-blockquote:bg-slate-50 prose-blockquote:py-0.5 prose-blockquote:not-italic",
  "dark:prose-blockquote:border-indigo-500 dark:prose-blockquote:bg-slate-800/40",
].join(" ");

export function OutputPanel(p: Props) {
  const [tab, setTab] = useState<Tab>("preview");
  const [copied, setCopied] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const thinkRef = useRef<HTMLPreElement>(null);

  // Auto-scroll while streaming
  useEffect(() => {
    if (!p.streaming) return;
    const el = tab === "reasoning" ? thinkRef.current : scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [p.markdown, p.thinking, p.streaming, tab]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const copy = async () => {
    await navigator.clipboard.writeText(p.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const doExport = async (f: ExportFormat) => {
    setExporting(f);
    setMenuOpen(false);
    try {
      await p.onExport(f);
    } finally {
      setExporting(null);
    }
  };

  const hasOutput = p.markdown.trim().length > 0;
  const canExport = !!p.docId && hasOutput && !p.streaming;
  const words = hasOutput ? p.markdown.trim().split(/\s+/).length : 0;
  const seconds = ((p.streaming ? p.elapsedMs : (p.durationMs ?? 0)) / 1000).toFixed(1);

  return (
    <section className="card flex min-h-0 flex-col">
      <header className="divider flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
        <div className="segmented" role="tablist">
          {(
            [
              ["preview", "Preview", Eye],
              ["markdown", "Markdown", FileCode2],
              ["reasoning", "Reasoning", Brain],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                tab === key ? "seg-on" : "seg-off"
              }`}
            >
              <Icon className="size-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {p.dirty && (
            <button
              onClick={p.onSave}
              disabled={p.saving}
              className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-amber-600 disabled:opacity-60"
            >
              {p.saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
              Save edits
            </button>
          )}
          <button onClick={copy} disabled={!hasOutput} className="btn-outline">
            {copied ? <Check className="size-3.5 text-emerald-600 dark:text-emerald-400" /> : <Copy className="size-3.5" />}
            {copied ? "Copied" : "Copy"}
          </button>
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((o) => !o)}
              disabled={!canExport || !!exporting}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              title={p.dirty ? "Save edits first to include them in the export" : undefined}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 disabled:opacity-40 dark:bg-indigo-500 dark:hover:bg-indigo-600"
            >
              {exporting ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
              Export
              <ChevronDown className="size-3" />
            </button>
            {menuOpen && (
              <div role="menu" className="popover absolute right-0 z-20 mt-1.5 w-56 overflow-hidden py-1">
                {EXPORTS.map((e) => (
                  <button
                    key={e.key}
                    role="menuitem"
                    onClick={() => doExport(e.key)}
                    className="hover-row block w-full px-3.5 py-2 text-left"
                  >
                    <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{e.label}</div>
                    <div className="ink-muted text-xs">{e.hint}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      {(p.streaming || p.durationMs !== null) && (
        <div className="divider ink-muted flex items-center gap-3 border-b bg-slate-50/60 px-5 py-2 text-xs dark:bg-slate-800/30">
          {p.streaming && p.phase === "queued" ? (
            <span className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
              <Clock className="size-3.5" />
              Queued{p.queuePosition > 0 ? ` — position ${p.queuePosition}` : ""}
            </span>
          ) : p.streaming ? (
            <span className="flex items-center gap-1.5 font-medium text-indigo-600 dark:text-indigo-400">
              <Loader2 className="size-3.5 animate-spin" />
              {p.phase === "thinking" ? "Reasoning…" : "Writing…"}
            </span>
          ) : (
            <span className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
              <Check className="size-3.5" /> Done
            </span>
          )}
          {p.chunk && p.chunk.total > 1 && (
            <span>
              Part {p.chunk.index}/{p.chunk.total}
            </span>
          )}
          <span>{seconds}s</span>
          <span>{words.toLocaleString()} words</span>
          {p.dirty && <span className="text-amber-600 dark:text-amber-400">· unsaved edits</span>}
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        {tab === "preview" && (
          <div ref={scrollRef} className="absolute inset-0 overflow-y-auto">
            {hasOutput ? (
              <article className={`${PROSE} ${p.streaming && p.phase === "writing" ? "blink-caret" : ""}`}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{p.markdown}</ReactMarkdown>
              </article>
            ) : (
              <EmptyState streaming={p.streaming} queued={p.phase === "queued"} position={p.queuePosition} />
            )}
          </div>
        )}

        {tab === "markdown" && (
          <textarea
            value={p.markdown}
            onChange={(e) => p.onEdit(e.target.value)}
            readOnly={p.streaming}
            aria-label="Formatted Markdown"
            placeholder="Formatted Markdown will appear here. You can edit it directly."
            spellCheck={false}
            className="absolute inset-0 resize-none rounded-b-2xl bg-transparent p-6 font-mono text-[13px] leading-relaxed text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-200 dark:placeholder:text-slate-500"
          />
        )}

        {tab === "reasoning" && (
          <pre
            ref={thinkRef}
            className="ink-muted absolute inset-0 overflow-y-auto p-6 font-mono text-xs leading-relaxed whitespace-pre-wrap"
          >
            {p.thinking || "The model's reasoning trace will appear here while it works."}
          </pre>
        )}
      </div>
    </section>
  );
}

function EmptyState({ streaming, queued, position }: { streaming: boolean; queued: boolean; position: number }) {
  const [title, body] = queued
    ? [
        position > 1 ? `Waiting in line — ${position - 1} job(s) ahead` : "Up next…",
        "The model handles one document at a time. You can leave this page; the job keeps running and its result is saved to history.",
      ]
    : streaming
      ? [
          "The model is reading your document…",
          "gpt-oss reasons first, then writes. Peek at the Reasoning tab to watch it think. You can leave this page; the job keeps running.",
        ]
      : [
          "Your formatted document will appear here",
          "Paste text or upload a file, pick a format, and hit Format. Output streams live and is saved to your history.",
        ];
  return (
    <div className="grid h-full place-items-center p-8">
      <div className="max-w-sm text-center">
        <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-50 to-violet-100 text-indigo-600 dark:from-indigo-500/15 dark:to-violet-500/15 dark:text-indigo-300">
          {queued ? (
            <Clock className="size-6" />
          ) : streaming ? (
            <Loader2 className="size-6 animate-spin" />
          ) : (
            <Sparkles className="size-6" />
          )}
        </div>
        <h3 className="ink-strong mt-4 text-base font-semibold">{title}</h3>
        <p className="ink-muted mt-1.5 text-sm">{body}</p>
      </div>
    </div>
  );
}
