export type ExecutableVersion = {
  agent_id: string;
  name: string;
  version: number;
  model_id: string;
  model_provider: string;
  config_hash: string;
  local_preview: true;
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
