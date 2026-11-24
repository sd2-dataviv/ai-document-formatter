import { ChevronDown, FileUp, Loader2, Paperclip, RotateCcw, Square, Wand2, X } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "../api";
import type { Template, ThinkLevel } from "../types";
import { TemplateIcon } from "./TemplateIcon";

export interface InputState {
  title: string;
  text: string;
  sourceFilename: string | null;
  templateId: number | null;
  customInstructions: string;
  think: ThinkLevel;
}

interface Props {
  value: InputState;
  onChange: (patch: Partial<InputState>) => void;
  templates: Template[];
  busy: boolean;
  isExisting: boolean;
  onFormat: () => void;
  onStop: () => void;
  onError: (msg: string) => void;
}

const ACCEPT = ".txt,.md,.markdown,.docx,.pdf,.html,.htm,.csv,.log,.json,.xml,.yaml,.yml,.rst";
const LABEL = "ink-muted mb-1.5 block text-xs font-medium";

export function InputPanel({ value, onChange, templates, busy, isExisting, onFormat, onStop, onError }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(!!value.customInstructions);

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const res = await api.extract(file);
      onChange({
        text: res.text,
        sourceFilename: res.filename,
        title: value.title || res.title,
      });
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const words = value.text.trim() ? value.text.trim().split(/\s+/).length : 0;
  const canFormat = value.text.trim().length > 0 && !busy && !uploading;

  return (
    <section className="card flex min-h-0 flex-col">
      <header className="divider flex items-center justify-between border-b px-5 py-3.5">
        <h2 className="ink-strong text-sm font-semibold">Source</h2>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
          <button onClick={() => fileRef.current?.click()} disabled={busy || uploading} className="btn-outline">
            {uploading ? <Loader2 className="size-3.5 animate-spin" /> : <FileUp className="size-3.5" />}
            Upload file
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5">
        <div>
          <label htmlFor="doc-title" className={LABEL}>
            Title (optional)
          </label>
          <input
            id="doc-title"
            value={value.title}
            onChange={(e) => onChange({ title: e.target.value })}
            placeholder="Leave blank to let the AI pick one"
            className="field px-3 py-2"
          />
        </div>

        <div
          className={`relative flex min-h-56 flex-1 flex-col rounded-xl border-2 border-dashed transition ${
            dragging ? "border-indigo-400 bg-indigo-50/50 dark:bg-indigo-500/10" : "border-transparent"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) handleFile(f);
          }}
        >
          <div className="mb-1.5 flex items-center justify-between">
            <label htmlFor="doc-text" className="ink-muted text-xs font-medium">
              Raw text
            </label>
            {value.sourceFilename && (
              <span className="ink-muted flex items-center gap-1 rounded-full bg-slate-100 py-0.5 pr-1 pl-2 text-xs dark:bg-slate-800">
                <Paperclip className="size-3" />
                <span className="max-w-48 truncate">{value.sourceFilename}</span>
                <button
                  aria-label="Remove file reference"
                  onClick={() => onChange({ sourceFilename: null })}
                  className="rounded-full p-0.5 hover:bg-slate-200 dark:hover:bg-slate-700"
                >
                  <X className="size-3" />
                </button>
              </span>
            )}
          </div>
          <textarea
            id="doc-text"
            value={value.text}
            onChange={(e) => onChange({ text: e.target.value })}
            placeholder={
              "Paste messy notes, an email thread, a transcript, a draft…\n\nOr drag & drop a PDF, DOCX, TXT, MD or HTML file here."
            }
            className="field min-h-48 flex-1 resize-none px-3 py-2.5 font-mono text-[13px] leading-relaxed"
          />
          <div className="ink-faint mt-1 text-right text-[11px]">
            {words.toLocaleString()} words · {value.text.length.toLocaleString()} chars
          </div>
          {dragging && (
            <div className="pointer-events-none absolute inset-0 grid place-items-center rounded-xl text-sm font-medium text-indigo-600 dark:text-indigo-300">
              Drop file to extract text
            </div>
          )}
        </div>

        <div>
          <span className="ink-muted mb-2 block text-xs font-medium">Format as</span>
          <div className="grid grid-cols-2 gap-2 2xl:grid-cols-3">
            {templates.map((t) => {
              const active = t.id === value.templateId;
              return (
                <button
                  key={t.id}
                  title={t.description}
                  aria-pressed={active}
                  onClick={() => onChange({ templateId: active ? null : t.id })}
                  className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-xs font-medium transition ${
                    active
                      ? "selected border-indigo-500 ring-1 ring-indigo-500"
                      : "border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800"
                  }`}
                >
                  <TemplateIcon
                    name={t.icon}
                    className={`size-4 shrink-0 ${active ? "text-indigo-600 dark:text-indigo-300" : "ink-faint"}`}
                  />
                  <span className="truncate">{t.name}</span>
                </button>
              );
            })}
          </div>
          {value.templateId && (
            <p className="ink-muted mt-2 text-xs">{templates.find((t) => t.id === value.templateId)?.description}</p>
          )}
        </div>

        <div>
          <button
            onClick={() => setShowAdvanced((s) => !s)}
            aria-expanded={showAdvanced}
            className="ink-muted flex items-center gap-1 text-xs font-medium hover:text-slate-900 dark:hover:text-slate-100"
          >
            <ChevronDown className={`size-3.5 transition ${showAdvanced ? "" : "-rotate-90"}`} />
            Advanced options
          </button>
          {showAdvanced && (
            <div className="mt-3 space-y-4">
              <div>
                <label htmlFor="doc-instructions" className={LABEL}>
                  Custom instructions
                </label>
                <textarea
                  id="doc-instructions"
                  value={value.customInstructions}
                  onChange={(e) => onChange({ customInstructions: e.target.value })}
                  rows={3}
                  placeholder="e.g. Use British English. Keep it under one page. Add a table of contents."
                  className="field resize-y px-3 py-2"
                />
              </div>
              <div>
                <span className={LABEL}>Reasoning effort</span>
                <div className="segmented inline-flex" role="radiogroup" aria-label="Reasoning effort">
                  {(["low", "medium", "high"] as ThinkLevel[]).map((lvl) => (
                    <button
                      key={lvl}
                      role="radio"
                      aria-checked={value.think === lvl}
                      onClick={() => onChange({ think: lvl })}
                      className={`rounded-md px-3.5 py-1.5 text-xs font-medium capitalize transition ${
                        value.think === lvl ? "seg-on" : "seg-off"
                      }`}
                    >
                      {lvl}
                    </button>
                  ))}
                </div>
                <p className="ink-faint mt-1.5 text-[11px]">
                  Higher effort = better structure on complex docs, but slower.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      <footer className="divider border-t p-4">
        {busy ? (
          <button
            onClick={onStop}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600"
          >
            <Square className="size-3.5 fill-current" /> Stop generating
          </button>
        ) : (
          <button
            onClick={onFormat}
            disabled={!canFormat}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:from-indigo-700 hover:to-violet-700 disabled:cursor-not-allowed disabled:opacity-40 dark:from-indigo-500 dark:to-violet-500 dark:hover:from-indigo-600 dark:hover:to-violet-600"
          >
            {isExisting ? <RotateCcw className="size-4" /> : <Wand2 className="size-4" />}
            {isExisting ? "Re-format document" : "Format document"}
          </button>
        )}
      </footer>
    </section>
  );
}
