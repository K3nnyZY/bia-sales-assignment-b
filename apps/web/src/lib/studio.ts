export type Principal = {
  id: string;
  name: string;
  role: string;
  permissions: string[];
  active: boolean;
};
export type Agent = {
  id: string;
  name: string;
  description: string;
  department: string;
  owner_id: string;
  status: "draft" | "disabled" | "deprecated";
  revision: number;
  created_at: string;
};
export type CatalogModel = {
  id: string;
  name: string;
  provider: string;
  model_identifier: string;
  release: string;
  profile: string;
  capabilities: string[];
  context_window: number;
  max_output_tokens: number;
  status: string;
  data_policy: string;
};
export type CatalogTool = {
  id: string;
  name: string;
  version: string;
  description: string;
  permissions: string[];
  operation: string;
  status: string;
  input_schema: object;
  output_schema: object;
};
export type Configuration = {
  api_version: "bia.ai/v1";
  kind: "AgentConfiguration";
  objective: string;
  instructions: string;
  model: {
    model_id: string;
    profile?: string | null;
    max_output_tokens: number;
  };
  tool_ids: string[];
  required_capabilities: string[];
  limits: {
    max_steps: number;
    max_tool_calls: number;
    timeout_seconds: number;
  };
  security: {
    require_authentication: true;
    resource_scope: "caller_owned";
    allow_financial_writes: false;
  };
};
export type AgentVersion = {
  agent_id: string;
  number: number;
  source_version: number | null;
  status: "draft" | "snapshot";
  revision: number;
  model_id: string;
  configuration: Configuration;
  snapshot: object | null;
  config_hash: string | null;
  created_by: string;
  created_at: string;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function studioRequest<T>(
  path: string,
  token: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/studio${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const result = await response.json();
      if (Array.isArray(result.detail))
        message = result.detail
          .map(
            (item: { loc: string[]; msg: string }) =>
              `${item.loc.join(".")}: ${item.msg}`,
          )
          .join("; ");
      else message = result.detail?.message || result.detail || message;
    } catch {
      /* Preserve the HTTP status when the response is not JSON. */
    }
    throw new ApiError(response.status, String(message));
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export function allowedStudioPath(segments: string[]): boolean {
  if (
    !segments.length ||
    segments.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part))
  )
    return false;
  return /^(me|users|models(?:\/[a-z][a-z0-9_-]{2,79})?|tools(?:\/[a-z][a-z0-9_-]{2,79})?|agents(?:\/[a-z][a-z0-9_-]{2,79}(?:\/versions(?:\/[1-9]\d*(?:\/snapshot)?)?)?)?)$/.test(
    segments.join("/"),
  );
}
