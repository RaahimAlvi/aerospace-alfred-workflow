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
  move-focused-to-workspace)
    if [[ -z "$arg" ]]; then
      echo "Missing workspace name" >&2
      exit 1
    fi
    aerospace move-node-to-workspace "$arg"
    ;;
  move-focused-to-workspace-follow)
    if [[ -z "$arg" ]]; then
      echo "Missing workspace name" >&2
      exit 1
    fi
    aerospace move-node-to-workspace --focus-follows-window "$arg"
    ;;
  move-window-to-workspace)
    if [[ -z "$arg" ]]; then
      echo "Missing workspace name" >&2
      exit 1
    fi
    if [[ -z "${window_id:-}" ]]; then
      echo "Missing window id" >&2
      exit 1
    fi
    aerospace move-node-to-workspace --window-id "$window_id" "$arg"
    ;;
  move-window-to-workspace-follow)
    if [[ -z "$arg" ]]; then
      echo "Missing workspace name" >&2
      exit 1
    fi
    if [[ -z "${window_id:-}" ]]; then
      echo "Missing window id" >&2
      exit 1
    fi
    aerospace move-node-to-workspace --focus-follows-window --window-id "$window_id" "$arg"
    ;;
  move-focused-direction)
    if [[ -z "${direction:-}" ]]; then
      echo "Missing direction" >&2
      exit 1
    fi
    aerospace move "$direction"
    ;;
  swap-focused-direction)
    if [[ -z "${direction:-}" ]]; then
      echo "Missing direction" >&2
      exit 1
    fi
    aerospace swap "$direction"
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
