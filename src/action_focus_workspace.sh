#!/bin/bash
set -euo pipefail

workspace="${1:-}"
if [[ -z "$workspace" ]]; then
  echo "Missing workspace name" >&2
  exit 1
fi

aerospace workspace "$workspace"
