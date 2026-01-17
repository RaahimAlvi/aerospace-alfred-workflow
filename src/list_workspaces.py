#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from typing import Optional, Tuple


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


CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


def get_cache_path() -> str:
    cache_root = os.environ.get("XDG_CACHE_HOME")
    if not cache_root:
        cache_root = os.path.expanduser("~/Library/Caches")
    cache_dir = os.path.join(cache_root, "aerospace-alfred-workflow")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "icon_cache.json")


def load_icon_cache() -> dict:
    cache_path = get_cache_path()
    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def save_icon_cache(cache: dict) -> None:
    cache_path = get_cache_path()
    try:
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(cache, handle)
    except OSError:
        return


def fetch_all_windows() -> list[dict]:
    raw_windows = run_command(
        [
            "aerospace",
            "list-windows",
            "--all",
            "--format",
            "%{window-id}\t%{app-bundle-id}\t%{app-name}\t%{window-title}\t%{workspace}",
        ]
    )
    windows = []
    for line in raw_windows.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 4)
        while len(parts) < 5:
            parts.append("")
        window_id, bundle_id, app_name, window_title, workspace = parts
        windows.append(
            {
                "window-id": int(window_id) if window_id else None,
                "app-bundle-id": bundle_id,
                "app-name": app_name,
                "window-title": window_title,
                "workspace": workspace,
            }
        )
    return windows


def fetch_bindings() -> dict:
    raw_bindings = run_command(
        ["aerospace", "config", "--get", "mode.main.binding", "--json"]
    )
    bindings = json.loads(raw_bindings)
    return bindings


def resolve_app_path(
    bundle_id: str, cache: dict[str, dict]
) -> Tuple[Optional[str], bool]:
    if not bundle_id:
        return None, False
    if bundle_id in cache:
        entry = cache[bundle_id]
        if isinstance(entry, dict):
            ts = entry.get("ts", 0)
            path = entry.get("path", "")
            if ts and (time.time() - ts) < CACHE_TTL_SECONDS:
                return (path or None), False
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
    if app_path and not os.path.exists(app_path):
        app_path = None
    cache[bundle_id] = {"path": app_path or "", "ts": int(time.time())}
    return app_path, True


def build_workspace_items(
    workspaces: list[str],
    query: str,
    include_empty: bool,
    mode: str,
    counts_by_workspace: dict[str, int],
    window_id: Optional[str] = None,
    enable_autocomplete: bool = False,
) -> list[dict]:
    items = []
    query_lower = query.lower()
    for name in workspaces:
        if query_lower and query_lower not in name.lower():
            continue
        count = counts_by_workspace.get(name, 0)
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


def build_window_items(
    workspace: str, windows: list[dict], query: str, icon_cache: dict
) -> Tuple[list[dict], bool]:
    items = []
    cache_updated = False
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
        app_path, updated = resolve_app_path(bundle_id, icon_cache)
        if updated:
            cache_updated = True
        if app_path:
            item["icon"] = {"type": "fileicon", "path": app_path}
        items.append(item)
    return items, cache_updated


def build_workspace_action_items(workspace: str) -> list[dict]:
    return [
        {
            "title": f"Focus workspace {workspace}",
            "subtitle": "Switch to this workspace",
            "arg": workspace,
            "variables": {
                "action": "focus-workspace",
                "workspace": workspace,
            },
        },
        {
            "title": f"Move focused window to {workspace}",
            "subtitle": "Move focused window only",
            "arg": workspace,
            "variables": {
                "action": "move-focused-to-workspace",
                "workspace": workspace,
            },
        },
        {
            "title": f"Move focused window to {workspace} and follow",
            "subtitle": "Move window and switch to destination",
            "arg": workspace,
            "variables": {
                "action": "move-focused-to-workspace-follow",
                "workspace": workspace,
            },
        },
        {
            "title": f"List windows in workspace {workspace}",
            "subtitle": "Drill into workspace windows",
            "autocomplete": f"{workspace} ",
            "valid": False,
        },
    ]


def build_arrange_items() -> list[dict]:
    items = []
    for direction in ("left", "right", "up", "down"):
        items.append(
            {
                "title": f"Move focused window {direction}",
                "subtitle": "Reorder window within layout",
                "arg": direction,
                "variables": {
                    "action": "move-focused-direction",
                    "direction": direction,
                },
            }
        )
    for direction in ("left", "right", "up", "down"):
        items.append(
            {
                "title": f"Swap focused window {direction}",
                "subtitle": "Swap with adjacent window",
                "arg": direction,
                "variables": {
                    "action": "swap-focused-direction",
                    "direction": direction,
                },
            }
        )
    return items


def build_hotkey_items(bindings: dict, query: str) -> list[dict]:
    items = []
    query_lower = query.lower()
    for hotkey, action in bindings.items():
        title = str(action)
        subtitle = str(hotkey)
        haystack = f"{title} {subtitle}".lower()
        if query_lower and query_lower not in haystack:
            continue
        items.append(
            {
                "title": title,
                "subtitle": subtitle,
                "arg": subtitle,
                "text": {"copy": subtitle, "largetype": subtitle},
            }
        )
    return items


def main() -> int:
    query = " ".join(sys.argv[1:]).strip()
    icon_cache = load_icon_cache()
    try:
        workspaces = fetch_workspaces()
        windows = fetch_all_windows()
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        payload = alfred_error_item(
            "AeroSpace workspace query failed",
            f"{exc}",
        )
        print(json.dumps(payload))
        return 1

    counts_by_workspace: dict[str, int] = {name: 0 for name in workspaces}
    windows_by_workspace: dict[str, list[dict]] = {}
    for window in windows:
        workspace = window.get("workspace") or ""
        if workspace:
            counts_by_workspace[workspace] = counts_by_workspace.get(workspace, 0) + 1
            windows_by_workspace.setdefault(workspace, []).append(window)

    if query:
        first_token = query.split()[0]
        remainder = query[len(first_token) :].strip()
        if first_token in {"command", "commands", "hotkey", "hotkeys", "keys", "help"}:
            try:
                bindings = fetch_bindings()
            except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                payload = alfred_error_item(
                    "Failed to load AeroSpace keybindings",
                    f"{exc}",
                )
                print(json.dumps(payload))
                return 1
            items = build_hotkey_items(bindings, remainder)
            print(json.dumps({"items": items}))
            return 0
        if first_token == "move":
            items = build_workspace_items(
                workspaces,
                remainder,
                include_empty=True,
                mode="move-focused",
                counts_by_workspace=counts_by_workspace,
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
                    counts_by_workspace=counts_by_workspace,
                    window_id=window_id,
                    enable_autocomplete=False,
                )
                print(json.dumps({"items": items}))
                return 0
        if first_token in {"action", "actions"}:
            tokens = query.split()
            if len(tokens) >= 2:
                workspace = tokens[1]
                if workspace in workspaces:
                    items = build_workspace_action_items(workspace)
                    print(json.dumps({"items": items}))
                    return 0
            items = build_workspace_items(
                workspaces,
                remainder,
                include_empty=True,
                mode="browse",
                counts_by_workspace=counts_by_workspace,
                enable_autocomplete=False,
            )
            for item in items:
                item["subtitle"] = "Actions for this workspace"
                item["autocomplete"] = f"action {item['arg']} "
                item["valid"] = False
            print(json.dumps({"items": items}))
            return 0
        if first_token == "arrange":
            items = build_arrange_items()
            print(json.dumps({"items": items}))
            return 0
        if first_token in workspaces:
            workspace_windows = windows_by_workspace.get(first_token, [])
            items, cache_updated = build_window_items(
                first_token, workspace_windows, remainder, icon_cache
            )
            if cache_updated:
                save_icon_cache(icon_cache)
            print(json.dumps({"items": items}))
            return 0

    items = build_workspace_items(
        workspaces,
        query,
        include_empty=False,
        mode="browse",
        counts_by_workspace=counts_by_workspace,
        enable_autocomplete=True,
    )
    print(json.dumps({"items": items}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
