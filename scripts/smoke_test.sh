#!/usr/bin/env bash
# End-to-end smoke test: drives the three workflows over real HTTP calls and
# asserts on the JSON they return. This is the "proof it runs" command.
#
#   ./scripts/smoke_test.sh              # against http://localhost:5688
#   N8N_URL=... ./scripts/smoke_test.sh  # against another host
set -uo pipefail

BASE="${N8N_URL:-http://localhost:5688}"
SAMPLES="$(cd "$(dirname "$0")/.." && pwd)/samples"
fails=0
checks=0

say()  { printf '%s\n' "$*"; }
ok()   { checks=$((checks + 1)); printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
bad()  { checks=$((checks + 1)); fails=$((fails + 1)); printf '  \033[31mFAIL\033[0m  %s\n    %s\n' "$1" "$2"; }
expect() { # expect <label> <needle> <haystack>
  case "$3" in
    *"$2"*) ok "$1" ;;
    *) bad "$1" "expected to find '$2' in: $(printf '%s' "$3" | cut -c1-300)" ;;
  esac
}

say "waiting for the workflows to be live at $BASE ..."
# n8n's HTTP port answers before it finishes registering the published webhooks,
# so wait until a real webhook call comes back with real workflow output.
ready=0
for _ in $(seq 1 90); do
  out=$(curl -sS -X POST "$BASE/webhook/lead-gen/process" -H 'Content-Type: application/json' \
    -d '{"name":"readiness","email":"readiness@example.com","message":"readiness probe"}' 2>/dev/null)
  case "$out" in
    *'"tier"'*) ready=1; break ;;
  esac
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  say "the demos are not responding at $BASE (run: make up)"
  exit 1
fi
say "n8n is up and the workflows are live."

say ""
say "01 invoice automation (multipart PDF upload, binary field 'data')"
r=$(curl -sS -X POST "$BASE/webhook/doc-automation/process" -F "data=@$SAMPLES/invoice_001.pdf")
expect "invoice_001.pdf -> status PASS" '"status":"PASS"' "$r"
expect "invoice_001.pdf -> extracted the printed total" '"total":538.92' "$r"
r=$(curl -sS -X POST "$BASE/webhook/doc-automation/process" -F "data=@$SAMPLES/invoice_003.pdf")
expect "invoice_003.pdf -> status REVIEW (deliberate total mismatch caught)" '"status":"REVIEW"' "$r"
expect "invoice_003.pdf -> transcribes the printed (wrong) total" '"total":1200' "$r"
expect "invoice_003.pdf -> reports which check failed" 'total matches subtotal + tax' "$r"

say ""
say "02 lead generation & scoring"
r=$(curl -sS -X POST "$BASE/webhook/lead-gen/process" -H 'Content-Type: application/json' -d '{
  "name":"Dana Reyes","email":"dana@brightsmilesclinic.com","company":"Bright Smiles Clinic","website":"https://brightsmilesclinic.com",
  "message":"We need to automate our patient intake and invoice processing asap. We have a budget of around 2000 USD for the first phase and want it done this week."
}')
expect "hot lead -> tier HOT" '"tier":"HOT"' "$r"
expect "hot lead -> no phone call proposed" '"followup_email"' "$r"

r=$(curl -sS -X POST "$BASE/webhook/lead-gen/process" -H 'Content-Type: application/json' -d '{
  "name":"Sam","email":"sam@example.com","message":"just looking around"
}')
expect "vague lead -> tier COLD" '"tier":"COLD"' "$r"

say ""
say "03 AI support agent (webchat + human handoff)"
r=$(curl -sS -X POST "$BASE/webhook/support-agent/chat" -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke-1","messages":[{"role":"user","content":"how much is the gluten-free bread?"}]}')
expect "price question -> answered without handoff" '"handoff":false' "$r"
expect "price question -> uses the documented price" '8' "$r"

r=$(curl -sS -X POST "$BASE/webhook/support-agent/chat" -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke-2","messages":[{"role":"user","content":"I want a refund for yesterday order, this is unacceptable"}]}')
expect "refund request -> handoff true" '"handoff":true' "$r"
expect "refund request -> escalation reason logged" 'handoff_reason' "$r"

say ""
if [ "$fails" -eq 0 ]; then
  say "✅ all $checks checks passed"
else
  say "❌ $fails of $checks checks failed"
fi
exit "$([ "$fails" -eq 0 ] && echo 0 || echo 1)"
