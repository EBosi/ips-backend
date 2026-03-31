#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/ips_api.py"

if [[ -z "${SCOPUS_API_KEY:-}" && -z "${WOS_API_KEY:-}" ]]; then
  echo "Set at least one provider key before running this script." >&2
  exit 1
fi

if [[ -n "${SCOPUS_API_KEY:-}" ]]; then
  echo "[scopus] author retrieval"
  python3 "$PYTHON_SCRIPT" scopus-author --author-id 7004212771 >/tmp/ips_scopus_author.json
  echo "  saved /tmp/ips_scopus_author.json"
fi

if [[ -n "${SCOPUS_API_KEY:-}" ]]; then
  echo "[scopus] publication search"
  python3 "$PYTHON_SCRIPT" scopus-pubs --author-id 7004212771 --start-year 2022 --end-year 2026 --normalized >/tmp/ips_scopus_pubs.json
  echo "  saved /tmp/ips_scopus_pubs.json"
fi

if [[ -n "${WOS_API_KEY:-}" ]]; then
  echo "[wos] document search"
  python3 "$PYTHON_SCRIPT" wos-pubs --query 'AI=Emanuele Bosi' --normalized >/tmp/ips_wos_pubs.json
  echo "  saved /tmp/ips_wos_pubs.json"
fi
