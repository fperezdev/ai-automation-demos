#!/bin/sh
# Import the workflows from ./workflows into this n8n instance, activate them and
# start n8n. Idempotent: the workflow JSONs carry their ids, so re-importing
# overwrites the same rows instead of duplicating them.
set -e

IMPORT_DIR=/tmp/import
LLM_HOST="${LLM_HOST:-mock-llm}"

mkdir -p "$IMPORT_DIR"
for file in /workflows/*.json; do
  base=$(basename "$file")
  # The workflows ship pointing at a local router on 127.0.0.1:8770. Inside the
  # compose network that address is n8n itself, so rewrite it to the mock LLM
  # service (or to whatever host was passed in LLM_HOST).
  sed "s|http://127.0.0.1:8770|http://${LLM_HOST}:8770|g" "$file" > "$IMPORT_DIR/$base"
done

echo "[entrypoint] importing $(ls -1 "$IMPORT_DIR" | wc -l) workflows from /workflows"
n8n import:workflow --separate --input="$IMPORT_DIR"

echo "[entrypoint] publishing workflows (required for the production webhook URLs to respond)"
for file in /workflows/*.json; do
  id=$(grep -m1 '"id"' "$file" | sed 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
  if [ -z "$id" ]; then
    echo "[entrypoint]   skipping $file (no workflow id found)"
    continue
  fi
  echo "[entrypoint]   publish $id"
  n8n publish:workflow --id="$id"
done

echo "[entrypoint] starting n8n"
exec n8n start
