#!/usr/bin/env python3
import json
import subprocess
import sys
from typing import Optional


def run_command(args: list[str]) -> str:
    result = subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def alfred_error_item(title: str, subtitle: str) -> dict:
    return {
        "items": [
            {
                "title": title,
                "subtitle": subtitle,
                "valid": False,
            }
        ]
    }


def fetch_workspaces() -> list[str]:
    raw_workspaces = run_command(["aerospace", "list-workspaces", "--all", "--json"])
    workspaces = json.loads(raw_workspaces)
    names = []
    for workspace_entry in workspaces:
        name = workspace_entry.get("workspace")
        if name:
            names.append(name)
    return names


def count_windows(workspace: str) -> int:
    raw_count = run_command(
        ["aerospace", "list-windows", "--workspace", workspace, "--count"]
    )
    return int(raw_count.strip() or "0")


def fetch_windows(workspace: str) -> list[dict]:
    raw_windows = run_command(
        [
            "aerospace",
            "list-windows",
            "--workspace",
            workspace,
            "--format",
            "%{window-id}\t%{app-bundle-id}\t%{app-name}\t%{window-title}",
        ]
    )
    windows = []
    for line in raw_windows.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        while len(parts) < 4:
            parts.append("")
        window_id, bundle_id, app_name, window_title = parts
        windows.append(
            {
                "window-id": int(window_id) if window_id else None,
                "app-bundle-id": bundle_id,
                "app-name": app_name,
                "window-title": window_title,
            }
        )
    return windows


def resolve_app_path(bundle_id: str, cache: dict[str, Optional[str]]) -> Optional[str]:
    if not bundle_id:
        return None
    if bundle_id in cache:
        return cache[bundle_id]
    app_path = None
    try:
        raw_paths = run_command(
            [
                "mdfind",
                f"kMDItemCFBundleIdentifier == '{bundle_id}'",
            ]
        )
        app_path = raw_paths.splitlines()[0].strip() if raw_paths.strip() else None
    except subprocess.CalledProcessError:
        app_path = None
    if not app_path:
        try:
            raw_path = run_command(
                [
                    "osascript",
                    "-e",
                    f'POSIX path of (path to application id "{bundle_id}")',
                ]
            )
            app_path = raw_path.strip() if raw_path.strip() else None
        except subprocess.CalledProcessError:
            app_path = None
    cache[bundle_id] = app_path
    return app_path


def build_workspace_items(
    workspaces: list[str],
    query: str,
    include_empty: bool,
    mode: str,
    window_id: Optional[str] = None,
    enable_autocomplete: bool = False,
) -> list[dict]:
    items = []
    query_lower = query.lower()
    for name in workspaces:
        if query_lower and query_lower not in name.lower():
            continue
        try:
            count = count_windows(name)
        except (subprocess.CalledProcessError, ValueError):
            count = 0
        if count <= 0 and not include_empty:
            continue

        if count == 0:
            subtitle = "empty"
        else:
            window_label = "window" if count == 1 else "windows"
            subtitle = f"{count} {window_label}"

        if mode == "browse":
            action = "focus-workspace"
        elif mode == "move-focused":
            action = "move-focused-to-workspace"
        elif mode == "move-window":
            action = "move-window-to-workspace"
        else:
            action = "focus-workspace"

        variables = {"action": action, "workspace": name}
        if mode == "move-window" and window_id:
            variables["window_id"] = window_id

        item = {
            "title": f"Workspace {name}",
            "subtitle": subtitle,
            "arg": name,
            "uid": f"workspace-{name}",
            "variables": variables,
        }
        if enable_autocomplete:
            item["autocomplete"] = f"{name} "

        if mode == "browse":
            item["mods"] = {
                "cmd": {
                    "subtitle": f"Move focused window to workspace {name}",
                    "arg": name,
                    "variables": {
                        "action": "move-focused-to-workspace",
                        "workspace": name,
                    },
                },
                "alt": {
                    "subtitle": f"Move focused window to workspace {name} and follow",
                    "arg": name,
                    "variables": {
                        "action": "move-focused-to-workspace-follow",
                        "workspace": name,
                    },
                },
            }
        elif mode == "move-focused":
            item["mods"] = {
                "alt": {
                    "subtitle": f"Move focused window to workspace {name} and follow",
                    "arg": name,
                    "variables": {
                        "action": "move-focused-to-workspace-follow",
                        "workspace": name,
                    },
                }
            }
        elif mode == "move-window":
            item["mods"] = {
                "alt": {
                    "subtitle": f"Move window to workspace {name} and follow",
                    "arg": name,
                    "variables": {
                        "action": "move-window-to-workspace-follow",
                        "workspace": name,
                        "window_id": window_id or "",
                    },
                }
            }

        items.append(item)
    return items


def build_window_items(workspace: str, windows: list[dict], query: str) -> list[dict]:
    items = []
    icon_cache: dict[str, Optional[str]] = {}
    query_lower = query.lower()
    for window in windows:
        app_name = window.get("app-name") or "Unknown App"
        window_title = window.get("window-title") or ""
        window_id = window.get("window-id")
        bundle_id = window.get("app-bundle-id") or ""
        haystack = f"{app_name} {window_title}".lower()
        if query_lower and query_lower not in haystack:
            continue

        title = window_title if window_title else app_name
        subtitle = app_name if window_title else "Window"
        if window_id is not None:
            subtitle = f"{subtitle} - ID {window_id}"
        item = {
            "title": title,
            "subtitle": subtitle,
            "arg": str(window_id) if window_id is not None else "",
            "variables": {
                "action": "focus-window",
                "workspace": workspace,
                "window_id": str(window_id) if window_id is not None else "",
            },
        }
        if window_id is not None:
            item["autocomplete"] = f"move-window {window_id} "
        if window_id is not None:
            item["uid"] = f"window-{window_id}"
        app_path = resolve_app_path(bundle_id, icon_cache)
        if app_path:
            item["icon"] = {"type": "fileicon", "path": app_path}
        items.append(item)
    return items


def main() -> int:
    query = " ".join(sys.argv[1:]).strip()
    try:
        workspaces = fetch_workspaces()
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        payload = alfred_error_item(
            "AeroSpace workspace query failed",
            f"{exc}",
        )
        print(json.dumps(payload))
        return 1

    if query:
        first_token = query.split()[0]
        remainder = query[len(first_token) :].strip()
        if first_token == "move":
            items = build_workspace_items(
                workspaces,
                remainder,
                include_empty=True,
                mode="move-focused",
                enable_autocomplete=False,
            )
            print(json.dumps({"items": items}))
            return 0
        if first_token == "move-window":
            tokens = query.split()
            if len(tokens) >= 2:
                window_id = tokens[1]
                remainder_start = len(tokens[0]) + len(tokens[1]) + 1
                remainder = query[remainder_start:].strip()
                items = build_workspace_items(
                    workspaces,
                    remainder,
                    include_empty=True,
                    mode="move-window",
                    window_id=window_id,
                    enable_autocomplete=False,
                )
                print(json.dumps({"items": items}))
                return 0
        if first_token in workspaces:
            try:
                windows = fetch_windows(first_token)
            except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                payload = alfred_error_item(
                    f"Failed to list windows for workspace {first_token}",
                    f"{exc}",
                )
                print(json.dumps(payload))
                return 1
            items = build_window_items(first_token, windows, remainder)
            print(json.dumps({"items": items}))
            return 0

    items = build_workspace_items(
        workspaces,
        query,
        include_empty=False,
        mode="browse",
        enable_autocomplete=True,
    )
    print(json.dumps({"items": items}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
