// Mirror of REQUIREMENTS.md §4 / backend/witness/models.py. Field names must match the API exactly.
export type Label = "supported" | "unsupported" | "contradicted";
export type FinalLabel = Label | "needs_review";

export interface Sentence { id: string; text: string }
export interface Passage { id: string; doc: string; text: string; sentences: Sentence[] }
export interface Claim { id: string; text: string; start: number; end: number }

export interface JudgeVerdict {
  claim_id: string;
  judge: "gemma" | "nli";
  label: Label;
  evidence_ids: string[];
  explanation: string;
  confidence: number | null;
}

export interface FinalVerdict {
  claim_id: string;
  label: FinalLabel;
  evidence_ids: string[];
  explanation: string;
  gemma: JudgeVerdict | null;
  nli: JudgeVerdict | null;
  single_judge: boolean;
}

export interface TrustScore {
  supported: number;
  unsupported: number;
  contradicted: number;
  needs_review: number;
  total: number;
  percent_supported: number;
}

export interface PipelineResult {
  question: string;
  answer_text: string;
  answer_source: "gemma-4-e2b-local" | "pasted";
  passages: Passage[];
  claims: Claim[];
  verdicts: FinalVerdict[];
  trust: TrustScore;
  fixed_answer: string;
  timings: Record<string, number>;
  errors: string[];
  mode: "live" | "replay";
}

export interface Health {
  status: string;
  version: string;
  lmstudio: boolean;
  gemini_key: boolean;
  nli_loaded: boolean;
  embeddings_loaded: boolean;
  kb_passages: number;
  replay_default: boolean;
  models: { writer: string; judge_1: string; judge_2: string };
}

// A PDF the person uploaded: it replaces the event handbook as the source documents for their checks.
export interface DocumentInfo { id: string; name: string; pages: number; passages: number; sentences: number; words: number }

export interface DemoQuestion { id: string; question: string; expect: FinalLabel; why: string }
export interface BackupAnswer { id: string; question: string; answer: string; source: string; is_example: boolean }
export interface ReplayEntry { key: string; question: string; answer_source: PipelineResult["answer_source"]; saved_at: string }

export interface EvalRow { judge: "gemma" | "nli" | "combined"; label: string; accuracy: number; correct: number; n: number }
export interface EvalResult {
  is_example: boolean;
  note: string;
  n_claims: number;
  generated_at: string;
  rows: EvalRow[];
  per_label: Record<string, { n: number }>;
}
