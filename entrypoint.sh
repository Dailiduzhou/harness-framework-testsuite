#!/bin/bash
# Container entrypoint — expand env vars in opencode config
set -e

expanded() {
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line//'${DEEPSEEK_BASE_URL}'/$DEEPSEEK_BASE_URL}"
        line="${line//'${DEEPSEEK_API_KEY}'/$DEEPSEEK_API_KEY}"
        printf '%s\n' "$line"
    done
}

if [ -f /app/config/opencode.json ]; then
    mkdir -p /root/.config/opencode
    expanded < /app/config/opencode.json > /root/.config/opencode/opencode.json
fi

exec "$@"
