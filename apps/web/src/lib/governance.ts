export type Governance = {
  agent_id: string;
  version_number: number;
  config_hash: string;
  stage: string;
  revision: number;
  latest_evaluation_id: string | null;
  approval_id: string | null;
  ever_published: boolean;
  publication_version: number | null;
  publication_revision: number;
  publication_enabled: boolean;
  gate: { eligible: boolean; reasons: string[]; evaluation_id: string | null };
};
export type Suite = {
  id: string;
  version: number;
  name: string;
  suite_hash: string;
  checks: string[];
};
export type Evaluation = {
  id: string;
  agent_id: string;
  version_number: number;
  config_hash: string;
  suite_id: string;
  suite_version: number;
  suite_hash: string;
  environment_hash: string;
  mode: string;
  runner_version: string;
  status: string;
  total: number;
  passed_count: number;
  critical_failures: number;
  started_at: string;
};
export type EvaluationDetail = {
  evaluation: Evaluation;
  results: {
    check: string;
    critical: boolean;
    passed: boolean;
    error_code: string | null;
    details: Record<string, unknown>;
    run_id: string | null;
    duration_ms: number;
  }[];
};
export type Approval = {
  id: string;
  agent_id: string;
  version_number: number;
  status: string;
  requested_by: string;
  decided_by: string | null;
  reason: string;
};
export type Audit = {
  id: string;
  actor_id: string;
  action: string;
  agent_id: string | null;
  version_number: number | null;
  details: object;
  created_at: string;
};
export type Metrics = {
  runs: number;
  completed: number;
  failed: number;
  denied: number;
  escalated: number;
  running: number;
  latency_avg_ms: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  tool_calls: number;
  tool_errors: number;
  scope: string;
  evaluation_runs_excluded: boolean;
  models: {
    model_id: string;
    mode: string;
    runs: number;
    input_tokens: number | null;
    output_tokens: number | null;
    estimated_cost_usd: string | null;
    input_tokens_known_runs: number;
    output_tokens_known_runs: number;
    cost_known_runs: number;
  }[];
};
