import type {
  DocumentFull,
  DocumentSummary,
  ExportFormat,
  ExtractResult,
  FormatRequest,
  Health,
  JobCreated,
  StreamEvent,
  Template,
  TemplateInput,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (body?.detail) {
      detail = typeof body.detail === "string" ? body.detail : (body.detail[0]?.msg ?? JSON.stringify(body.detail));
    }
    if (res.status >= 500 && body?.request_id) detail += ` (request ${body.request_id})`;
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(detail, res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection.", 0);
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),

  templates: () => request<Template[]>("/api/templates"),
  createTemplate: (t: TemplateInput) => request<Template>("/api/templates", json("POST", t)),
  updateTemplate: (id: number, t: Partial<TemplateInput>) => request<Template>(`/api/templates/${id}`, json("PUT", t)),
  deleteTemplate: (id: number) => request<void>(`/api/templates/${id}`, { method: "DELETE" }),

  documents: (q = "") => request<DocumentSummary[]>(`/api/documents?q=${encodeURIComponent(q)}`),
  document: (id: number) => request<DocumentFull>(`/api/documents/${id}`),
  updateDocument: (id: number, body: { title?: string; formatted_markdown?: string }) =>
    request<DocumentFull>(`/api/documents/${id}`, json("PUT", body)),
  deleteDocument: (id: number) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),

  extract: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ExtractResult>("/api/extract", { method: "POST", body: form });
  },

  createJob: (req: FormatRequest) => request<JobCreated>("/api/jobs", json("POST", req)),
  cancelJob: (documentId: number) => request<void>(`/api/jobs/${documentId}/cancel`, { method: "POST" }),

  /**
   * Follow a job's NDJSON event stream until the server closes it. The first event is always a
   * `snapshot` of progress so far, so this is safe to call again after a dropped connection.
   */
  async streamJob(documentId: number, onEvent: (ev: StreamEvent) => void, signal: AbortSignal) {
    const res = await fetch(`${BASE}/api/jobs/${documentId}/events`, { signal });
    if (!res.ok || !res.body) throw await toApiError(res);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl: number;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) onEvent(JSON.parse(line) as StreamEvent);
      }
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer) as StreamEvent);
  },

  exportUrl: (id: number, format: ExportFormat) => `${BASE}/api/documents/${id}/export?format=${format}`,
};

export async function downloadExport(id: number, format: ExportFormat) {
  const res = await fetch(api.exportUrl(id, format));
  if (!res.ok) throw await toApiError(res);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename\*=UTF-8''([^;]+)/.exec(disposition);
  const filename = match ? decodeURIComponent(match[1]) : `document.${format}`;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
