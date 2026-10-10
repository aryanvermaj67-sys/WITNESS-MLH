// Small HTTP client for the backend (REQUIREMENTS.md §5). Never throws: every call returns a typed result.
import type { BackupAnswer, DemoQuestion, DocumentInfo, EvalResult, Health, PipelineResult, ReplayEntry } from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const TIMEOUT = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? 90000);

export type Reply<T> = { ok: true; data: T } | { ok: false; error: string; status?: number };

async function request<T>(path: string, init?: RequestInit, timeout = TIMEOUT): Promise<Reply<T>> {
  // fetch has no timeout of its own
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(BASE + path, { ...init, signal: ctrl.signal });
    if (!res.ok) {
      // the backend explains upload problems in plain words ("That file is not a PDF."): show those as they are
      const detail = await res.json().then((j: { detail?: unknown }) => (typeof j.detail === "string" ? j.detail : null), () => null);
      const error = detail && res.status !== 404 ? detail
        : res.status === 422 ? "The question must be 1 to 500 characters (and a pasted answer at most 4,000)."
        : res.status === 404 ? "Not found." : `The backend answered with an error (HTTP ${res.status}).`;
      return { ok: false, status: res.status, error };
    }
    return { ok: true, data: (await res.json()) as T };
  } catch (e) {
    const timedOut = e instanceof DOMException && e.name === "AbortError";
    return { ok: false, error: timedOut ? "The check took too long and was stopped." : "The backend can't be reached." };
  } finally {
    clearTimeout(timer);
  }
}

export const getHealth = () => request<Health>("/api/health", undefined, 5000);
export const getDemoQuestions = () => request<DemoQuestion[]>("/api/demo-questions", undefined, 8000);
export const getBackupAnswers = () => request<BackupAnswer[]>("/api/backup-answers", undefined, 8000);
export const getEval = () => request<EvalResult>("/api/eval", undefined, 8000);

export const check = (question: string, answerText?: string, documentId?: string | null) =>
  request<PipelineResult>("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, answer_text: answerText || null, mode: "live", document_id: documentId || null }),
  });

// Uploaded PDFs live in the backend's memory only. The request body is the raw file.
export const getDocuments = () => request<DocumentInfo[]>("/api/documents", undefined, 5000);
export const uploadDocument = (file: File) =>
  request<DocumentInfo>(`/api/documents?name=${encodeURIComponent(file.name)}`, {
    method: "POST", headers: { "Content-Type": "application/pdf" }, body: file,
  }, 120000); // reading and indexing a long PDF takes a few seconds
export const deleteDocument = (id: string) => request<{ deleted: string }>(`/api/documents/${encodeURIComponent(id)}`, { method: "DELETE" }, 5000);

// Replay: the backend first, then the static copy in public/replay (works with the backend switched off).
export async function getReplayIndex(): Promise<Reply<ReplayEntry[]>> {
  const live = await request<ReplayEntry[]>("/api/replay", undefined, 4000);
  return live.ok ? live : request<ReplayEntry[]>("/replay/index.json", undefined, 4000);
}

export async function getReplay(key: string): Promise<Reply<PipelineResult>> {
  const live = await request<PipelineResult>(`/api/replay/${encodeURIComponent(key)}`, undefined, 4000);
  if (live.ok) return live;
  const file = await request<PipelineResult>(`/replay/${encodeURIComponent(key)}.json`, undefined, 4000);
  // saved files hold the live result: label it as replay here so it can never pass for a live one
  return file.ok ? { ok: true, data: { ...file.data, mode: "replay" } } : live;
}
