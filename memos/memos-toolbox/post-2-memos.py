#!/usr/bin/env python3

import os
import json
import glob
import requests
import sys
from typing import List

# default placeholders (can be overridden via environment)
DEFAULT_BASE = os.environ.get("MEMOS_BASE_URL")
DEFAULT_TOKEN = os.environ.get("MEMOS_TOKEN")
DEFAULT_DIR = os.path.join(os.path.dirname(__file__), "memos_ready")

def parse_visibility(v):
    """Parse visibility value from env or prompt.

    Returns either an int (if numeric provided) or the string name the server accepts
    (e.g. 'PUBLIC', 'PROTECTED', 'PRIVATE'). Default is 'PUBLIC'.
    """
    if v is None:
        return "PUBLIC"
    v = str(v).strip()
    if v.isdigit():
        try:
            return int(v)
        except ValueError:
            return "PUBLIC"
    lower = v.lower()
    if lower in ("public", "pub", "p"):
        return "PUBLIC"
    if lower in ("protected", "prot"):
        return "PROTECTED"
    if lower in ("private", "priv", "pri"):
        return "PRIVATE"
    # fallback to PUBLIC
    return "PUBLIC"


def prompt(prompt_text: str, default: str = "") -> str:
    """Prompt with a default value (shown in brackets)."""
    if not sys.stdin.isatty():
        # non-interactive; return default
        return default
    if default:
        raw = input(f"{prompt_text} [{default}]: ").strip()
    else:
        raw = input(f"{prompt_text}: ").strip()
    return raw or default


def choose_files(md_files: List[str]) -> List[str]:
    if not md_files:
        print("No .md files found.")
        return []
    print("Found the following markdown files:")
    for i, p in enumerate(md_files, start=1):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                first = fh.read(200).replace("\n", " ")
        except Exception:
            first = "(unable to read preview)"
        print(f"  {i:3d}) {os.path.basename(p)} - {first[:80]}{'...' if len(first)>80 else ''}")

    sel = prompt("Select files to post (e.g. 1,3-5) or 'all'", "all")
    if sel.strip().lower() in ("all", "a", "*"):
        return md_files

    chosen: List[str] = []
    parts = [s.strip() for s in sel.split(",") if s.strip()]
    for part in parts:
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                start_i = int(start)
                end_i = int(end)
                for idx in range(start_i, end_i + 1):
                    if 1 <= idx <= len(md_files):
                        chosen.append(md_files[idx - 1])
            except Exception:
                continue
        else:
            try:
                idx = int(part)
                if 1 <= idx <= len(md_files):
                    chosen.append(md_files[idx - 1])
            except Exception:
                # try matching by name
                for p in md_files:
                    if os.path.basename(p) == part:
                        chosen.append(p)
    # dedupe while preserving order
    seen = set()
    out = []
    for p in chosen:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def confirm_posting_for_files(files: List[str], base: str, token: str, vis, dry: bool):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    base = base.rstrip("/")
    all_yes = False
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
        except Exception as e:
            print(f"Skipping {path}: cannot read ({e})")
            continue

        preview = content[:400].replace("\n", " ")
        print('\n' + '-' * 60)
        print(f"File: {os.path.basename(path)} | visibility={vis} | dry_run={dry}")
        print(preview + ("..." if len(content) > 400 else ""))
        if not sys.stdin.isatty():
            choice = 'y' if not dry else 'n'
        elif all_yes:
            choice = 'y'
        else:
            choice = input("Post this file? [y/N/a=q] (y=yes, n=no, a=all yes, q=quit): ").strip().lower()

        if choice == 'q':
            print("Quitting.")
            break
        if choice == 'a':
            all_yes = True
            choice = 'y'
        if choice != 'y':
            print(f"Skipping {os.path.basename(path)}")
            continue

        payload = {"content": content, "visibility": vis}
        if dry:
            print(f"DRY RUN: would POST {os.path.basename(path)} -> visibility={vis}")
            print(json.dumps({"content": content[:200].replace('\n', ' ')+("..." if len(content)>200 else ""), "visibility": vis}))
            continue

        try:
            r = requests.post(f"{base}/api/v1/memos", headers=headers, data=json.dumps(payload), timeout=30)
        except Exception as e:
            print(f"ERR {os.path.basename(path)} -> request failed: {e}")
            continue

        if r.ok:
            try:
                jr = r.json()
            except Exception:
                jr = {}
            name = jr.get("name")
            memo_id = None
            if isinstance(name, str) and "/" in name:
                memo_id = name.split("/", 1)[1]
            if memo_id is None:
                memo_id = jr.get('id')
            print(f"[OK] {os.path.basename(path)} -> name={name} id={memo_id}")
        else:
            print(f"ERR {os.path.basename(path)} -> {r.status_code}: {r.text}")


def main():
    # Gather defaults from environment but prompt interactively when possible
    # prefer environment values when both base and token exist so we can run non-interactively
    env_base = (DEFAULT_BASE or "").strip()
    env_token = (DEFAULT_TOKEN or "").strip()

    if env_base and env_token:
        # both provided via env -> use them and skip prompts
        base = env_base
        token = env_token
        print("Using MEMOS_BASE_URL and MEMOS_TOKEN from environment; skipping prompts.")
    else:
        # ensure prompt defaults are strings (not None) so prompt() shows a sensible default
        base = prompt("Memos base URL", env_base)
        token = prompt("Memos token (leave blank to use MEMOS_TOKEN env)", env_token)

    # Basic validation: base URL is required for posting
    if not base:
        print("No Memos base URL provided. Set the MEMOS_BASE_URL environment variable or provide a URL when prompted.")
        return
    dirp = prompt("Directory containing .md files", os.environ.get("MEMOS_DIR", DEFAULT_DIR))
    vis_in = prompt("Visibility (public/protected/private or 0/1/2)", os.environ.get("MEMOS_VISIBILITY", "public"))
    vis = parse_visibility(vis_in)
    dry_in = prompt("Dry run? (yes/no)", "yes" if os.environ.get("MEMOS_DRY_RUN", "1") not in ("0", "false", "False") else "no")
    dry = str(dry_in).lower() not in ("0", "false", "no")

    md_files = sorted(glob.glob(os.path.join(dirp, "*.md")))
    chosen = choose_files(md_files)
    if not chosen:
        print("No files selected. Exiting.")
        return

    confirm_posting_for_files(chosen, base, token, vis, dry)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nInterrupted by user.')
