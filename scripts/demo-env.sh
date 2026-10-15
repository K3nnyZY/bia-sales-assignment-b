#!/bin/sh
# Add missing local demo settings to a Sprint 1 .env without replacing existing values.
set -eu
test -f .env || cp .env.example .env
while IFS= read -r line; do
    case "$line" in
        ENABLE_DEMO_AUTH=*|DEMO_ADMIN_TOKEN=*|DEMO_CREATOR_TOKEN=*|DEMO_VIEWER_TOKEN=*)
            key=${line%%=*}
            if ! grep -q "^${key}=" .env; then
                printf '\n%s\n' "$line" >> .env
            fi
            ;;
    esac
done < .env.example
printf '%s\n' 'Missing demo settings added; existing values preserved. Development/test only.'
