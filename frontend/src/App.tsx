import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, downloadExport } from "./api";
import { InputPanel, type InputState } from "./components/InputPanel";
import { OutputPanel } from "./components/OutputPanel";
import { Sidebar, type View } from "./components/Sidebar";
import { TemplatesView } from "./components/TemplatesView";
import { useTheme } from "./theme";
import {
  isActiveStatus,
  type DocumentFull,
  type DocumentSummary,
  type ExportFormat,
  type Health,
  type StreamEvent,
  type Template,
} from "./types";

const EMPTY_INPUT: InputState = {
  title: "",
  text: "",
  sourceFilename: null,
  templateId: null,
  customInstructions: "",
  think: "low",
};

const MAX_RECONNECTS = 8;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

type Phase = "idle" | "queued" | "thinking" | "writing";

interface Toast {
  id: number;
  kind: "error" | "success";
  msg: string;
}

export default function App() {
  const [theme, setTheme] = useTheme();
  const [view, setView] = useState<View>("workspace");
  const [health, setHealth] = useState<Health | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [search, setSearch] = useState("");

  // Workspace
  const [input, setInput] = useState<InputState>(EMPTY_INPUT);
  const [docId, setDocId] = useState<number | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [savedMarkdown, setSavedMarkdown] = useState("");
  const [thinking, setThinking] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [queuePosition, setQueuePosition] = useState(0);
  const [chunk, setChunk] = useState<{ index: number; total: number } | null>(null);
  const [startedAt, setStartedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const streamRef = useRef<AbortController | null>(null);

  const [toasts, setToasts] = useState<Toast[]>([]);
  const toast = useCallback((kind: Toast["kind"], msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 3000);
  }, []);
  const onError = useCallback((m: string) => toast("error", m), [toast]);

  // ------------------------------------------------------------------ data loading
  const searchRef = useRef(search);
  searchRef.current = search;
  const loadTemplates = useCallback(() => api.templates().then(setTemplates).catch((e) => onError(e.message)), [onError]);
  const loadDocuments = useCallback(
    () => api.documents(searchRef.current).then(setDocuments).catch(() => undefined),
    [],
  );

  useEffect(() => {
    loadTemplates();
    const poll = () => api.health().then(setHealth).catch(() => setHealth(null));
    poll();
    const t = setInterval(poll, 30000);
    return () => clearInterval(t);
  }, [loadTemplates]);

  useEffect(() => {
    const t = setTimeout(loadDocuments, 200);
    return () => clearTimeout(t);
  }, [search, loadDocuments]);

  // While any job is queued/running, refresh history so status dots stay current.
  const anyActive = documents.some((d) => isActiveStatus(d.status));
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(loadDocuments, 3000);
    return () => clearInterval(t);
  }, [anyActive, loadDocuments]);

  // Default to the first template once templates arrive
  useEffect(() => {
    if (templates.length && input.templateId === null && !docId && !input.text) {
      setInput((i) => ({ ...i, templateId: templates[0].id }));
    }
  }, [templates]); // eslint-disable-line react-hooks/exhaustive-deps

  // Elapsed timer while a job is running
  useEffect(() => {
    if (!streaming) return;
    const t = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(t);
  }, [streaming]);

  // Stop following any stream when the app unmounts
  useEffect(() => () => streamRef.current?.abort(), []);

  const dirty = !!docId && !streaming && markdown !== savedMarkdown;
  const confirmDiscard = () => !dirty || confirm("You have unsaved edits to the formatted document. Discard them?");

  // ------------------------------------------------------------------ document state
  /** Set the open document and mirror it in the URL hash so it is linkable. */
  const selectDoc = (id: number | null) => {
    setDocId(id);
    history.replaceState(null, "", id ? `#/doc/${id}` : window.location.pathname);
  };

  const applyDocument = (d: DocumentFull) => {
    selectDoc(d.id);
    setMarkdown(d.formatted_markdown);
    setSavedMarkdown(d.formatted_markdown);
    setDurationMs(isActiveStatus(d.status) ? null : d.duration_ms);
    setInput({
      title: d.title,
      text: d.original_text,
      sourceFilename: d.source_filename,
      templateId: d.template_id,
      customInstructions: d.custom_instructions,
      think: d.think_level,
    });
  };

  const resetOutput = () => {
    setThinking("");
    setChunk(null);
    setQueuePosition(0);
  };

  /** Stop following the current job's stream (the job itself keeps running on the server). */
  const detach = () => {
    streamRef.current?.abort();
    streamRef.current = null;
    setStreaming(false);
    setPhase("idle");
  };

  // ------------------------------------------------------------------ job streaming
  /** Returns true when the event ends the job. */
  const handleEvent = (ev: StreamEvent): boolean => {
    switch (ev.type) {
      case "snapshot":
        setMarkdown(ev.markdown);
        setThinking(ev.thinking);
        setChunk(ev.chunk);
        setQueuePosition(ev.queue_position);
        if (ev.status === "queued") setPhase("queued");
        else if (ev.status === "processing") setPhase(ev.markdown ? "writing" : "thinking");
        return false;
      case "queued":
        setQueuePosition(ev.position);
        setPhase("queued");
        return false;
      case "status":
        if (ev.status === "processing") {
          setPhase("thinking");
          setQueuePosition(0);
          setStartedAt(Date.now());
        }
        return false;
      case "chunk":
        setChunk({ index: ev.index, total: ev.total });
        setPhase("thinking");
        setThinking((t) => `${t}${t ? "\n\n" : ""}── Part ${ev.index}/${ev.total} ──\n`);
        return false;
      case "thinking":
        setThinking((t) => t + ev.text);
        return false;
      case "content":
        setPhase("writing");
        setMarkdown((m) => m + ev.text);
        return false;
      case "ping":
        return false;
      case "done":
        applyDocument(ev.document);
        toast("success", "Document formatted and saved");
        return true;
      case "cancelled":
        if (ev.document) applyDocument(ev.document);
        toast("error", "Formatting cancelled.");
        return true;
      case "error":
        if (ev.document) applyDocument(ev.document);
        onError(ev.message);
        return true;
    }
  };

  /** Follow a job, transparently reconnecting if the connection drops. */
  const follow = async (id: number) => {
    streamRef.current?.abort();
    const ctrl = new AbortController();
    streamRef.current = ctrl;
    setStreaming(true);
    setStartedAt(Date.now());
    setNow(Date.now());
    setDurationMs(null);

    let failures = 0;
    let finished = false;
    while (!ctrl.signal.aborted && !finished) {
      try {
        await api.streamJob(
          id,
          (ev) => {
            failures = 0;
            if (handleEvent(ev)) finished = true;
          },
          ctrl.signal,
        );
        if (finished || ctrl.signal.aborted) break;
      } catch (e) {
        if (ctrl.signal.aborted) break;
        if (e instanceof ApiError && e.status === 404) {
          onError("This document no longer exists.");
          break;
        }
      }
      // The stream closed without a terminal event: the network or server blipped.
      failures += 1;
      if (failures > MAX_RECONNECTS) {
        onError("Lost connection to the server. The job keeps running; reopen the document to check on it.");
        break;
      }
      await sleep(Math.min(500 * 2 ** failures, 8000));
    }

    if (streamRef.current === ctrl) {
      streamRef.current = null;
      setStreaming(false);
      setPhase("idle");
    }
    loadDocuments();
  };

  // ------------------------------------------------------------------ actions
  const openDocument = async (id: number) => {
    if (id === docId || !confirmDiscard()) return;
    try {
      const d = await api.document(id);
      detach();
      resetOutput();
      applyDocument(d);
      setView("workspace");
      if (isActiveStatus(d.status)) follow(d.id);
      else if (d.status === "failed" && d.error) onError(`Last run failed: ${d.error}`);
    } catch (e) {
      onError((e as Error).message);
    }
  };

  // Open the document linked in the URL hash (#/doc/12) on first load
  useEffect(() => {
    const m = /^#\/doc\/(\d+)$/.exec(window.location.hash);
    if (m) openDocument(Number(m[1]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const newDocument = () => {
    if (!confirmDiscard()) return;
    detach();
    selectDoc(null);
    setMarkdown("");
    setSavedMarkdown("");
    resetOutput();
    setDurationMs(null);
    setInput({ ...EMPTY_INPUT, templateId: templates[0]?.id ?? null });
    setView("workspace");
  };

  const deleteDocument = async (id: number) => {
    const target = documents.find((d) => d.id === id);
    const running = target && isActiveStatus(target.status);
    if (!confirm(running ? "This document is still being formatted. Cancel and delete it?" : "Delete this document?"))
      return;
    try {
      await api.deleteDocument(id);
      if (id === docId) {
        detach();
        selectDoc(null);
        setMarkdown("");
        setSavedMarkdown("");
        resetOutput();
        setDurationMs(null);
      }
      loadDocuments();
      toast("success", "Document deleted");
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const format = async () => {
    if (!input.text.trim() || !confirmDiscard()) return;
    setSubmitting(true);
    try {
      const job = await api.createJob({
        text: input.text,
        title: input.title,
        source_filename: input.sourceFilename,
        template_id: input.templateId,
        custom_instructions: input.customInstructions,
        think_level: input.think,
        document_id: docId,
      });
      selectDoc(job.document_id);
      setMarkdown("");
      resetOutput();
      setQueuePosition(job.queue_position);
      setPhase(job.status === "queued" ? "queued" : "thinking");
      loadDocuments();
      follow(job.document_id);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const stop = async () => {
    if (!docId) return;
    try {
      await api.cancelJob(docId);
    } catch (e) {
      // 409 means it already finished; the stream will deliver the final state.
      if (!(e instanceof ApiError && e.status === 409)) onError((e as Error).message);
    }
  };

  const saveEdits = async () => {
    if (!docId) return;
    setSaving(true);
    try {
      const d = await api.updateDocument(docId, { formatted_markdown: markdown });
      setSavedMarkdown(d.formatted_markdown);
      loadDocuments();
      toast("success", "Edits saved");
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const exportDoc = async (f: ExportFormat) => {
    if (!docId) return;
    try {
      if (dirty) {
        const d = await api.updateDocument(docId, { formatted_markdown: markdown });
        setSavedMarkdown(d.formatted_markdown);
      }
      await downloadExport(docId, f);
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <div className="flex h-full">
      <Sidebar
        view={view}
        onView={setView}
        documents={documents}
        activeId={docId}
        search={search}
        onSearch={setSearch}
        onOpen={openDocument}
        onDelete={deleteDocument}
        onNew={newDocument}
        health={health}
        theme={theme}
        onTheme={setTheme}
      />

      <main className="min-w-0 flex-1">
        {view === "workspace" ? (
          <div className="flex h-full flex-col">
            {health && (!health.llm.reachable || !health.llm.model_available) && (
              <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
                <AlertTriangle className="size-4" />
                {!health.llm.reachable
                  ? `Cannot reach Ollama at ${health.llm.url}. Formatting will fail until it is available.`
                  : `Model "${health.llm.model}" is not available on the Ollama server. Run: ollama pull ${health.llm.model}`}
              </div>
            )}
            <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 p-5 lg:grid-cols-[minmax(380px,2fr)_3fr]">
              <InputPanel
                value={input}
                onChange={(patch) => setInput((i) => ({ ...i, ...patch }))}
                templates={templates}
                busy={streaming || submitting}
                isExisting={!!docId}
                onFormat={format}
                onStop={stop}
                onError={onError}
              />
              <OutputPanel
                markdown={markdown}
                thinking={thinking}
                streaming={streaming}
                phase={phase}
                queuePosition={queuePosition}
                chunk={chunk}
                elapsedMs={now - startedAt}
                durationMs={durationMs}
                docId={docId}
                dirty={dirty}
                saving={saving}
                onEdit={setMarkdown}
                onSave={saveEdits}
                onExport={exportDoc}
              />
            </div>
          </div>
        ) : (
          <TemplatesView
            templates={templates}
            onChanged={loadTemplates}
            onUse={(id) => {
              setInput((i) => ({ ...i, templateId: id }));
              setView("workspace");
            }}
            onError={onError}
            onToast={(m) => toast("success", m)}
          />
        )}
      </main>

      <div className="pointer-events-none fixed right-5 bottom-5 z-50 flex w-96 max-w-[calc(100vw-2.5rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className={`pointer-events-auto flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm shadow-lg ${
              t.kind === "error"
                ? "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
                : "border-emerald-200 bg-white text-slate-800 dark:border-emerald-900/60 dark:bg-slate-900 dark:text-slate-100"
            }`}
          >
            {t.kind === "error" ? (
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-500" />
            ) : (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-500" />
            )}
            <span className="flex-1 break-words">{t.msg}</span>
            <button
              aria-label="Dismiss"
              onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}
              className="text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
            >
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
