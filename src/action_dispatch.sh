#!/bin/bash
set -euo pipefail

action="${action:-}"
arg="${1:-}"

if [[ -z "$action" ]]; then
  echo "Missing action variable" >&2
  exit 1
fi

case "$action" in
  focus-workspace)
    if [[ -z "$arg" ]]; then
      echo "Missing workspace name" >&2
      exit 1
    fi
    aerospace workspace "$arg"
    ;;
  focus-window)
    if [[ -z "$arg" ]]; then
      echo "Missing window id" >&2
      exit 1
    fi
    aerospace focus --window-id "$arg"
    ;;
  *)
    echo "Unknown action: $action" >&2
    exit 1
    ;;
esac
