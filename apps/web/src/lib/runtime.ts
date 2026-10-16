export type ExecutableVersion = {
  agent_id: string;
  name: string;
  version: number;
  model_id: string;
  model_provider: string;
  config_hash: string;
  local_preview: boolean;
  published: boolean;
  available_modes: ("deterministic" | "provider")[];
};

export type RunResult = {
  id: string;
  agent_id: string;
  version_number: number;
  caller_id: string;
  model_id: string;
  config_hash: string;
  workflow_version: string;
  mode: "deterministic" | "provider";
  status: "running" | "completed" | "denied" | "failed" | "escalated";
  channel: "preview" | "published" | "evaluation";
  evaluation_id: string | null;
  answer: string | null;
  error_code: string | null;
  calculations: Record<string, string | null>;
  references: string[];
  input_tokens: number | null;
  output_tokens: number | null;
  estimated_cost_usd: string | null;
  started_at: string;
  completed_at: string | null;
};

export type RunTrace = {
  run: RunResult;
  events: {
    step: number;
    node: string;
    status: string;
    error_code: string | null;
    started_at: string;
    duration_ms: number;
  }[];
  knowledge_searches: {
    id: string;
    duration_ms: number;
    embedding_version: string;
    mode: string;
    error_code: string | null;
    references: {
      reference: string;
      document_id: string;
      version: number;
      chunk: number;
    }[];
  }[];
  tool_calls: {
    id: string;
    tool_id: string;
    tool_version: string;
    arguments: object;
    result_references: string[];
    attempt: number;
    status: string;
    error_code: string | null;
    started_at: string;
    completed_at: string;
    duration_ms: number;
  }[];
};
