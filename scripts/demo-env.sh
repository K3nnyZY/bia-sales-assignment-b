#!/bin/sh
# Add missing local demo settings to a Sprint 1 .env without replacing existing values.
set -eu
test -f .env || cp .env.example .env
while IFS= read -r line; do
    case "$line" in
        ENABLE_DEMO_AUTH=*|ENABLE_LOCAL_RUNTIME=*|ENABLE_PROVIDER_RUNTIME=*|DEMO_*_TOKEN=*|RUNTIME_TIMEOUT_SECONDS=*|EVALUATION_TIMEOUT_SECONDS=*|MODEL_TIMEOUT_SECONDS=*|LANGSMITH_TRACING=*|LANGCHAIN_TRACING_V2=*|LITELLM_LOCAL_MODEL_COST_MAP=*)
            key=${line%%=*}
            if ! grep -q "^${key}=" .env; then
                printf '\n%s\n' "$line" >> .env
            fi
            ;;
    esac
done < .env.example
printf '%s\n' 'Missing demo settings added; existing values preserved. Development/test only.'
