export type ThinkLevel = "low" | "medium" | "high";
export type ExportFormat = "md" | "html" | "docx" | "pdf";
export type DocStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";

export const isActiveStatus = (s: DocStatus) => s === "queued" || s === "processing";

export interface Template {
  id: number;
  slug: string;
  name: string;
  description: string;
  icon: string;
  instructions: string;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface TemplateInput {
  name: string;
  description: string;
  icon: string;
  instructions: string;
}

export interface DocumentSummary {
  id: number;
  title: string;
  source_filename: string | null;
  template_id: number | null;
  template_name: string | null;
  model: string;
  status: DocStatus;
  duration_ms: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentFull extends DocumentSummary {
  original_text: string;
  formatted_markdown: string;
  custom_instructions: string;
  think_level: ThinkLevel;
  error: string | null;
}

export interface Health {
  status: "ok" | "degraded";
  database: boolean;
  llm: {
    reachable: boolean;
    url: string;
    model: string;
    model_available: boolean;
    error?: string;
  };
  jobs: { running: number; queued: number };
}

export interface ExtractResult {
  filename: string;
  title: string;
  text: string;
  characters: number;
}

export interface FormatRequest {
  text: string;
  title: string;
  source_filename: string | null;
  template_id: number | null;
  custom_instructions: string;
  think_level: ThinkLevel;
  document_id: number | null;
}

export interface JobCreated {
  document_id: number;
  status: DocStatus;
  queue_position: number;
}

export type StreamEvent =
  | {
      type: "snapshot";
      status: DocStatus;
      queue_position: number;
      chunk: { index: number; total: number } | null;
      markdown: string;
      thinking: string;
    }
  | { type: "queued"; position: number }
  | { type: "status"; status: DocStatus }
  | { type: "chunk"; index: number; total: number }
  | { type: "thinking"; text: string }
  | { type: "content"; text: string }
  | { type: "ping" }
  | { type: "done"; document: DocumentFull }
  | { type: "cancelled"; document: DocumentFull | null }
  | { type: "error"; message: string; document: DocumentFull | null };
