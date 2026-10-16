import { readFileSync } from "node:fs";
import { defineRailway, image, project, service, volume } from "railway/iac";

// Secrets stay in an ignored 0600 file. Never use --show-values or commit plan artifacts.
// Generate this file with: python3 scripts/railway_credentials.py
const secrets = JSON.parse(
  readFileSync(
    process.env.BIA_RAILWAY_SECRETS_FILE || new URL("../../.tools/railway-secrets.json", import.meta.url),
    "utf8",
  ),
) as { postgres_password: string; manifest: object };
if (!/^[a-f0-9]{64}$/.test(secrets.postgres_password)) {
  throw new Error("A generated database password is required");
}

export default defineRailway(() => {
  const data = volume("postgres-data", { region: "us-east4-eqdc4a", sizeMB: 1024 });
  const postgres = service("postgres", {
    source: image("pgvector/pgvector:0.8.7-pg16-bookworm", {
      autoUpdates: { type: "disabled" },
    }),
    replicas: { "us-east4-eqdc4a": 1 },
    env: {
      POSTGRES_USER: "bia",
      POSTGRES_DB: "bia_studio",
      POSTGRES_PASSWORD: secrets.postgres_password,
      PGDATA: "/var/lib/postgresql/data/pgdata",
    },
    volumeMounts: { "/var/lib/postgresql/data": data },
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
      limitOverride: { containers: { cpu: 1, memoryBytes: 512 * 1024 ** 2 } },
    },
  });
  const api = service("api", {
    root: "/",
    build: { builder: "DOCKERFILE", dockerfilePath: "apps/api/Dockerfile" },
    preDeploy: "sh scripts/railway-predeploy.sh",
    start: "sh scripts/start-api.sh",
    healthcheck: "/health/ready",
    healthcheckTimeout: 180,
    replicas: { "us-east4-eqdc4a": 1 },
    env: {
      APP_ENV: "production",
      ENABLE_DEMO_AUTH: "false",
      ENABLE_LOCAL_RUNTIME: "false",
      ENABLE_ACCESS_TOKEN_AUTH: "true",
      ENABLE_PUBLISHED_RUNTIME: "true",
      ENABLE_PROVIDER_RUNTIME: "false",
      LANGSMITH_TRACING: "false",
      LANGCHAIN_TRACING_V2: "false",
      LITELLM_LOCAL_MODEL_COST_MAP: "True",
      CORS_ORIGINS: "[]", // Browser uses the same-origin Next.js proxy.
      BIND_HOST: "::",
      PORT: "8000",
      POSTGRES_HOST: "${{postgres.RAILWAY_PRIVATE_DOMAIN}}",
      POSTGRES_PORT: "5432",
      POSTGRES_USER: postgres.env.POSTGRES_USER,
      POSTGRES_DB: postgres.env.POSTGRES_DB,
      POSTGRES_PASSWORD: postgres.env.POSTGRES_PASSWORD,
    },
    deploy: {
      preDeployTimeoutSeconds: 300,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
      limitOverride: { containers: { cpu: 2, memoryBytes: 2 * 1024 ** 3 } },
    },
  });
  const web = service("web", {
    root: "/",
    build: { builder: "DOCKERFILE", dockerfilePath: "apps/web/Dockerfile" },
    start: "node apps/web/server.js",
    healthcheck: "/health",
    replicas: { "us-east4-eqdc4a": 1 },
    env: {
      NODE_ENV: "production",
      HOSTNAME: "::",
      PORT: "3000",
      BACKEND_URL: "http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000",
    },
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
      limitOverride: { containers: { cpu: 1, memoryBytes: 512 * 1024 ** 2 } },
    },
  });
  return project("bia-agent-studio", { resources: [postgres, api, web, data] });
});
