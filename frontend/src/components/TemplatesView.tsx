import { Copy, Lock, Pencil, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Template, TemplateInput } from "../types";
import { TEMPLATE_ICONS, TemplateIcon } from "./TemplateIcon";

interface Props {
  templates: Template[];
  onChanged: () => void;
  onUse: (id: number) => void;
  onError: (msg: string) => void;
  onToast: (msg: string) => void;
}

const EMPTY: TemplateInput = { name: "", description: "", icon: "wand", instructions: "" };

export function TemplatesView({ templates, onChanged, onUse, onError, onToast }: Props) {
  const [editing, setEditing] = useState<{ id: number | null; data: TemplateInput } | null>(null);
  const [saving, setSaving] = useState(false);

  // Close the editor with Escape
  useEffect(() => {
    if (!editing) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setEditing(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing]);

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      if (editing.id) await api.updateTemplate(editing.id, editing.data);
      else await api.createTemplate(editing.data);
      onToast(editing.id ? "Template updated" : "Template created");
      setEditing(null);
      onChanged();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (t: Template) => {
    if (!confirm(`Delete template "${t.name}"?`)) return;
    try {
      await api.deleteTemplate(t.id);
      onToast("Template deleted");
      onChanged();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const builtin = templates.filter((t) => t.is_builtin);
  const custom = templates.filter((t) => !t.is_builtin);
  const set = (patch: Partial<TemplateInput>) => editing && setEditing({ ...editing, data: { ...editing.data, ...patch } });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-8 py-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h1 className="ink-strong text-2xl font-semibold">Templates</h1>
            <p className="ink-muted mt-1 text-sm">
              A template tells the model what shape the output should take. Duplicate a built-in one to tweak it.
            </p>
          </div>
          <button
            onClick={() => setEditing({ id: null, data: { ...EMPTY } })}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600"
          >
            <Plus className="size-4" /> New template
          </button>
        </div>

        <Section title="Your templates" empty="No custom templates yet — create one or duplicate a built-in.">
          {custom.map((t) => (
            <Card
              key={t.id}
              t={t}
              onUse={() => onUse(t.id)}
              actions={
                <>
                  <IconBtn title="Edit" onClick={() => setEditing({ id: t.id, data: pick(t) })}>
                    <Pencil className="size-3.5" />
                  </IconBtn>
                  <IconBtn title="Delete" danger onClick={() => remove(t)}>
                    <Trash2 className="size-3.5" />
                  </IconBtn>
                </>
              }
            />
          ))}
        </Section>

        <Section title="Built-in">
          {builtin.map((t) => (
            <Card
              key={t.id}
              t={t}
              onUse={() => onUse(t.id)}
              actions={
                <>
                  <span title="Built-in (read-only)" className="p-1.5 text-slate-300 dark:text-slate-600">
                    <Lock className="size-3.5" />
                  </span>
                  <IconBtn
                    title="Duplicate & edit"
                    onClick={() => setEditing({ id: null, data: { ...pick(t), name: `${t.name} (copy)` } })}
                  >
                    <Copy className="size-3.5" />
                  </IconBtn>
                </>
              }
            />
          ))}
        </Section>
      </div>

      {editing && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4 backdrop-blur-sm dark:bg-black/60"
          onClick={() => setEditing(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="template-dialog-title"
            className="surface w-full max-w-2xl rounded-2xl shadow-2xl ring-1 ring-transparent dark:ring-slate-800"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="divider flex items-center justify-between border-b px-6 py-4">
              <h2 id="template-dialog-title" className="ink-strong text-base font-semibold">
                {editing.id ? "Edit template" : "New template"}
              </h2>
              <button
                aria-label="Close"
                onClick={() => setEditing(null)}
                className="ink-faint rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="space-y-4 px-6 py-5">
              <div className="grid grid-cols-[1fr_auto] gap-4">
                <Field label="Name">
                  <input
                    autoFocus
                    value={editing.data.name}
                    onChange={(e) => set({ name: e.target.value })}
                    className="field px-3 py-2"
                    placeholder="e.g. Weekly Status Update"
                  />
                </Field>
                <Field label="Icon">
                  <div className="flex flex-wrap gap-1">
                    {Object.keys(TEMPLATE_ICONS)
                      .slice(0, 8)
                      .map((key) => (
                        <button
                          key={key}
                          type="button"
                          aria-label={key}
                          aria-pressed={editing.data.icon === key}
                          onClick={() => set({ icon: key })}
                          className={`grid size-9 place-items-center rounded-lg border ${
                            editing.data.icon === key
                              ? "selected border-indigo-500"
                              : "ink-muted border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
                          }`}
                        >
                          <TemplateIcon name={key} className="size-4" />
                        </button>
                      ))}
                  </div>
                </Field>
              </div>
              <Field label="Short description">
                <input
                  value={editing.data.description}
                  onChange={(e) => set({ description: e.target.value })}
                  className="field px-3 py-2"
                  placeholder="Shown as a hint in the template picker"
                />
              </Field>
              <Field label="Formatting instructions for the AI">
                <textarea
                  value={editing.data.instructions}
                  onChange={(e) => set({ instructions: e.target.value })}
                  rows={9}
                  className="field resize-y px-3 py-2 font-mono text-[13px] leading-relaxed"
                  placeholder={
                    "Describe the target structure, e.g.\nFormat as a weekly status update: H1 with the week, then 'Highlights', 'Progress' (table: Workstream | Status | Notes), 'Risks', 'Next week'."
                  }
                />
              </Field>
            </div>
            <div className="divider flex justify-end gap-2 border-t px-6 py-4">
              <button
                onClick={() => setEditing(null)}
                className="ink rounded-lg px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={save}
                disabled={saving || !editing.data.name.trim() || !editing.data.instructions.trim()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40 dark:bg-indigo-500 dark:hover:bg-indigo-600"
              >
                {saving ? "Saving…" : "Save template"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const pick = (t: Template): TemplateInput => ({
  name: t.name,
  description: t.description,
  icon: t.icon,
  instructions: t.instructions,
});

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="ink-muted mb-1.5 block text-xs font-medium">{label}</span>
      {children}
    </label>
  );
}

function Section({ title, empty, children }: { title: string; empty?: string; children: React.ReactNode[] }) {
  return (
    <div className="mt-8">
      <h2 className="ink-faint mb-3 text-xs font-semibold tracking-wider uppercase">{title}</h2>
      {children.length === 0 && empty ? (
        <div className="ink-muted rounded-xl border border-dashed border-slate-300 px-6 py-8 text-center text-sm dark:border-slate-700">
          {empty}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
      )}
    </div>
  );
}

function Card({ t, actions, onUse }: { t: Template; actions: React.ReactNode; onUse: () => void }) {
  return (
    <div className="group flex flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:shadow dark:border-slate-800 dark:bg-slate-900 dark:shadow-none dark:hover:border-slate-700">
      <div className="flex items-start gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300">
          <TemplateIcon name={t.icon} className="size-4.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="ink-strong truncate text-sm font-semibold">{t.name}</div>
          <div className="ink-muted mt-0.5 line-clamp-2 text-xs">{t.description || "No description"}</div>
        </div>
        <div className="flex shrink-0">{actions}</div>
      </div>
      <p className="ink-muted mt-3 line-clamp-3 flex-1 rounded-lg bg-slate-50 px-3 py-2 font-mono text-[11px] leading-relaxed dark:bg-slate-950">
        {t.instructions}
      </p>
      <button
        onClick={onUse}
        className="mt-3 self-start text-xs font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
      >
        Use this template →
      </button>
    </div>
  );
}

function IconBtn({
  children,
  title,
  onClick,
  danger,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      title={title}
      aria-label={title}
      onClick={onClick}
      className={`ink-faint rounded-lg p-1.5 transition ${
        danger
          ? "hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/15 dark:hover:text-rose-400"
          : "hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}
