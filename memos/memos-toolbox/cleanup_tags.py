#!/usr/bin/env python3
"""
cleanup_tags.py

Search memos for the specified tag(s) and remove them from the memo metadata.

Features:
- Accept comma-separated tags to remove (e.g. --tags tag1,tag2)
- Dry-run by default; use --apply to perform updates
- Optional --strip-hashtags to also remove literal "#tag" tokens from content
- Tries PATCH then PUT to update memos; if neither succeeds, reports error

Assumptions:
- The Memos API exposes memo updates via PATCH or PUT at /api/v1/memos/<id> with a JSON body
  containing at least {"content": ..., "tags": [...]}. If the server uses a different
  update endpoint, this script will show the intended payloads when run as dry-run.

Usage (example):
  export MEMOS_BASE_URL="http://127.0.0.1:5230"
  export MEMOS_TOKEN="<token>"
  python3 cleanup_tags.py --tags oldtag,typo --strip-hashtags --apply

"""
import argparse
import os
import re
import sys
from typing import List, Optional

import requests

# default placeholders (can be overridden via environment)
MEMOS_BASE_URL = "http://192.168.50.234:5230"
MEMOS_TOKEN = "eyJhbGciOiJIUzI1NiIsImtpZCI6InYxIiwidHlwIjoiSldUIn0.eyJuYW1lIjoiIiwiaXNzIjoibWVtb3MiLCJzdWIiOiIxIiwiYXVkIjpbInVzZXIuYWNjZXNzLXRva2VuIl0sImV4cCI6NDkxMDE2MDU5MCwiaWF0IjoxNzU2NTYwNTkwfQ.O8qCnAn0Og4I6jyz78EgIWB_jVuo-Jwl4pX3szAi-sU"

BASE = os.environ.get("MEMOS_BASE_URL", MEMOS_BASE_URL).rstrip("/")
TOKEN = os.environ.get("MEMOS_TOKEN", MEMOS_TOKEN)
# HTTP headers used for API requests (uses resolved TOKEN)
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def parse_args():
    p = argparse.ArgumentParser(description="Remove/cleanup tags from a self-hosted Memos instance")
    p.add_argument("--tags", required=False, help="Comma-separated tags to remove (without #). If omitted the script runs interactively")
    p.add_argument("--apply", action="store_true", help="Actually apply changes. Without this the script is a dry-run")
    p.add_argument("--strip-hashtags", action="store_true", help="Also remove literal #tag tokens from memo content")
    p.add_argument("--limit", type=int, default=0, help="Stop after processing this many memos (0 = unlimited)")
    p.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    p.add_argument("--manage", action="store_true", help="Interactive tag management mode")
    return p.parse_args()


def list_all_memos(timeout: float = 30.0):
    page_token = ""
    while True:
        url = f"{BASE}/api/v1/memos"
        if page_token:
            url += f"?pageToken={page_token}"
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        for m in data.get("memos", []):
            yield m
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break


def memo_id(memo: dict) -> str:
    val = memo.get("name") or memo.get("id") or ""
    return val.split("/")[-1]


def clean_content_remove_hashtags(content: str, targets: List[str]) -> str:
    # remove occurrences like "#tag", "#Tag," "#tag." respecting word boundaries
    if not content:
        return content
    out = content
    for t in targets:
        # regex: match #tag with optional punctuation after, keep surrounding spacing
        pattern = re.compile(rf"(?i)(?:#){re.escape(t)}\b")
        out = pattern.sub("", out)
    # collapse multiple spaces left by removals
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out


def update_memo(mid: str, payload: dict, timeout: float = 30.0) -> bool:
    """Try PATCH then PUT. Return True if update appears successful."""
    url = f"{BASE}/api/v1/memos/{mid}"
    # try PATCH
    try:
        r = requests.patch(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload, timeout=timeout)
        if r.ok:
            return True
    except requests.RequestException:
        pass
    # fallback to PUT
    try:
        r = requests.put(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload, timeout=timeout)
        if r.ok:
            return True
        # some servers return 204 No Content on success
        if r.status_code == 204:
            return True
    except requests.RequestException:
        pass
    return False


def gather_all_tags(timeout: float = 30.0):
    """Return a sorted list of unique tags (case-preserved) across all memos."""
    seen = {}
    for m in list_all_memos(timeout=timeout):
        for t in (m.get('tags') or []):
            key = t.lower()
            if key not in seen:
                seen[key] = t
    return [seen[k] for k in sorted(seen.keys())]


def gather_all_tags_with_counts(timeout: float = 30.0):
    """Return (display_list, mapping) where display_list contains strings like 'Tag (N)'
    and mapping maps display -> canonical tag (case-preserved).
    """
    seen = {}
    counts = {}
    for m in list_all_memos(timeout=timeout):
        for t in (m.get('tags') or []):
            key = t.lower()
            counts[key] = counts.get(key, 0) + 1
            if key not in seen:
                seen[key] = t

    keys = sorted(seen.keys())
    display_list = []
    mapping = {}
    for k in keys:
        display = f"{seen[k]} ({counts.get(k,0)})"
        display_list.append(display)
        mapping[display] = seen[k]
    return display_list, mapping


def prompt_choice(prompt: str, choices: list) -> Optional[str]:
    """Prompt user to pick from existing choices. New tags are not allowed here.
    Returns the selected choice or None if the user cancelled.
    """
    # interactive filtering: user can type '/<tag-name>' to filter the list
    def print_choices(listing):
        for i, c in enumerate(listing, 1):
            print(f" {i}) {c}")

    filtered = choices
    print(prompt)
    print("Type '/<tag-name>' to filter the list (case-insensitive). Type 'q' to exit.")
    print_choices(filtered)

    while True:
        v = input("Enter number or tag name (or '/<tag-name>'): ").strip()
        if not v:
            continue
        lv = v.lower()
        if lv in ('q', 'quit', 'exit'):
            return None
        if v.startswith('/'):
            term = v[1:].strip()
            if not term:
                filtered = choices
                print("Filter cleared.")
            else:
                filtered = [c for c in choices if term.lower() in c.lower()]
                if not filtered:
                    print(f"No matches for '{term}'.")
            print_choices(filtered)
            continue
        # numeric selection indexes into the filtered list
        if v.isdigit():
            idx = int(v)
            if 1 <= idx <= len(filtered):
                return filtered[idx-1]
            print(f"Invalid selection: {v}")
            continue
        # textual selection: try exact then case-insensitive match in filtered
        if v in filtered:
            return v
        for c in filtered:
            if c.lower() == v.lower():
                return c
            # if choices are displayed as "Name (N)", allow the user to type just the Name
            m = re.match(r'^(.*) \(\d+\)$', c)
            if m and m.group(1).strip().lower() == v.lower():
                return c
        print(f"Invalid tag name: {v}. Use a number or pick from the shown list.")


def confirm_yes_no(prompt: str):
    """Ask a yes/no question. Returns True for yes, False for no, None for abort/exit."""
    r = input(f"{prompt} (Type Yes or No, or 'q' to cancel): ").strip()
    if not r:
        return False
    rl = r.lower()
    if rl in ('q', 'quit', 'exit'):
        return None
    return rl == 'yes'


def run_interactive_manager(apply: bool = False, timeout: float = 30.0, limit: int = 0):
    """Interactive mode: list tags, choose target and action, perform with confirmation."""
    displays, mapping = gather_all_tags_with_counts(timeout=timeout)
    if not displays:
        print("No tags found in memos.")
        return

    target_display = prompt_choice("Select a target tag:", displays)
    if target_display is None:
        print("Aborted by user.")
        return
    # map back to canonical tag text
    target = mapping.get(target_display, target_display)
    target_clean = target.strip().lstrip('#').lower()

    actions = ['create', 'delete', 'replace', 'fix']
    action = prompt_choice("Select action:", actions)
    if action is None:
        print("Aborted by user.")
        return
    action = action.lower()

    # For replace, ask for replacement tag early so preview can include it
    replace_with = None
    if action == 'replace':
        replace_with = input('Enter new tag name to replace with: ').strip().lstrip('#')
        if not replace_with:
            print('No replacement tag provided. Aborting.')
            return

    # collect affected memos and show a preview before asking to confirm
    def collect_affected_memos():
        affected = []
        for m in list_all_memos(timeout=timeout):
            mid = memo_id(m)
            tags_meta = [t for t in (m.get('tags') or [])]
            tags_lower = [t.lower() for t in tags_meta]
            content = m.get('content') or ''

            has_meta = target_clean in tags_lower
            has_hash_in_content = f"#{target_clean}" in content.lower()
            if not has_meta and not has_hash_in_content:
                continue

            new_tags = [t for t in tags_meta if t.lower() != target_clean]
            # replace logic
            if action == 'replace' and has_meta:
                if replace_with and replace_with.lower() not in [t.lower() for t in new_tags]:
                    new_tags.append(replace_with)

            # fix action additional removals
            if action == 'fix' and has_meta:
                if target_clean == 'harvested' and 'planted' in tags_lower:
                    new_tags = [t for t in new_tags if t.lower() != 'planted']
                if target_clean == 'planted' and 'inventory' in tags_lower:
                    new_tags = [t for t in new_tags if t.lower() != 'inventory']
                if target_clean == 'inventory' and 'wishlist' in tags_lower:
                    new_tags = [t for t in new_tags if t.lower() != 'wishlist']

            # prepare snippet
            snippet_before = (content or '')[:120].replace('\n', ' ')
            affected.append({
                'id': mid,
                'meta_before': tags_meta,
                'meta_after': new_tags,
                'snippet_before': snippet_before,
            })
            if limit and len(affected) >= limit:
                break
        return affected

    affected = collect_affected_memos()
    total = len(affected)
    print(f"Will affect {total} memo(s) for action '{action}' on tag '{target}'.")
    # show up to 10 samples
    sample_count = min(10, total)
    if sample_count > 0:
        print(f"Showing {sample_count} example memo(s):")
        for a in affected[:sample_count]:
            print(f" - {a['id']}: tags_before={a['meta_before']} tags_after={a['meta_after']}")
            if a['snippet_before']:
                print(f"    snippet: {a['snippet_before']}")
    else:
        print("No memos matched the selection.")

    # safety confirmation after preview
    conf = confirm_yes_no("Confirm and apply the above changes?")
    if conf is None:
        print("Aborted by user.")
        return
    if conf is False:
        print("Aborted by user.")
        return

    # Perform actions
    if action == 'create':
        # Creating a tag directly isn't supported by the Memos API in this script.
        # If you want a tag to exist, create a memo manually with that tag in the Memos UI
        # or use an API call outside this script. This action is a no-op here.
        print("Create action: this script won't create a tag resource. Create a memo with the tag via the Memos UI/API if desired.")
        return

    # For delete/replace/fix we need to iterate memos
    processed = 0
    updated = 0
    errors = 0

    # (replace_with already collected prior to preview)

    # fix rules mapping
    allowed_fix = {'harvested', 'planted', 'inventory'}
    if action == 'fix' and target_clean not in allowed_fix:
        print(f"Fix action only allowed for: {sorted(list(allowed_fix))}. Aborting.")
        return

    for m in list_all_memos(timeout=timeout):
        if limit and processed >= limit:
            break
        processed += 1
        mid = memo_id(m)
        tags_meta = [t for t in (m.get('tags') or [])]
        tags_lower = [t.lower() for t in tags_meta]
        content = m.get('content') or ''

        has_meta = target_clean in tags_lower
        has_hash_in_content = f"#{target_clean}" in content.lower()
        if not has_meta and not has_hash_in_content:
            continue

        new_tags = [t for t in tags_meta if t.lower() != target_clean]
        # replace logic
        if action == 'replace' and has_meta:
            # add replacement tag if not present
            if replace_with and replace_with.lower() not in [t.lower() for t in new_tags]:
                new_tags.append(replace_with)

        # fix action additional removals
        if action == 'fix' and has_meta:
            if target_clean == 'harvested' and 'planted' in tags_lower:
                new_tags = [t for t in new_tags if t.lower() != 'planted']
            if target_clean == 'planted' and 'inventory' in tags_lower:
                new_tags = [t for t in new_tags if t.lower() != 'inventory']
            if target_clean == 'inventory' and 'wishlist' in tags_lower:
                new_tags = [t for t in new_tags if t.lower() != 'wishlist']

        # if strip hashtags, also clean content of literal hashtags
        new_content = content
        if args_strip_hashtags := False:
            # placeholder; interactive mode could ask, but preserve default behavior: don't strip
            pass

        if new_tags == tags_meta and new_content == content:
            continue

        print(f"Memo {mid}: meta_before={tags_meta} meta_after={new_tags}")
        if not apply:
            continue

        payload = {"content": new_content, "tags": new_tags}
        ok = update_memo(mid, payload, timeout=timeout)
        if ok:
            updated += 1
        else:
            errors += 1

    print(f"Interactive run done. Processed={processed} Updated={updated} Errors={errors}")


def main():
    args = parse_args()
    if not MEMOS_TOKEN:
        print("MEMOS_TOKEN environment variable is not set. Export it and re-run.", file=sys.stderr)
        sys.exit(1)

    # Interactive by default when --tags is not provided, or when --manage is used
    if args.manage or not args.tags:
        run_interactive_manager(apply=args.apply, timeout=args.timeout, limit=args.limit)
        return

    # non-interactive (existing) cleanup mode
    targets = [t.strip().lstrip('#').lower() for t in args.tags.split(',') if t.strip()]
    if not targets:
        print("No tags provided after parsing. Nothing to do.")
        return

    print(f"Searching memos for tags: {targets} (dry-run={not args.apply})")

    processed = 0
    updated = 0
    errors = 0

    for m in list_all_memos(timeout=args.timeout):
        if args.limit and processed >= args.limit:
            break
        processed += 1
        mid = memo_id(m)
        tags = [t for t in (m.get('tags') or [])]
        content = m.get('content') or ''

        # detect if any target tags present in metadata or as hashtags in content
        tags_lower = [t.lower() for t in tags]
        has_meta = any(t in tags_lower for t in targets)
        has_hash_in_content = any(f"#{t}" in content.lower() for t in targets)

        if not has_meta and not has_hash_in_content:
            continue

        new_tags = [t for t in tags if t.lower() not in targets]
        new_content = content
        if args.strip_hashtags and has_hash_in_content:
            new_content = clean_content_remove_hashtags(content, targets)

        if new_tags == tags and new_content == content:
            # nothing to do
            continue

        print(f"Memo {mid}: will remove tags {targets}. meta_before={tags} meta_after={new_tags}")
        if args.strip_hashtags and content != new_content:
            snippet_before = (content or '')[:120].replace('\n', ' ')
            snippet_after = (new_content or '')[:120].replace('\n', ' ')
            print(f" content before: {snippet_before}")
            print(f" content after:  {snippet_after}")

        if not args.apply:
            continue

        payload = {"content": new_content, "tags": new_tags}
        ok = update_memo(mid, payload, timeout=args.timeout)
        if ok:
            updated += 1
            print(f"Updated {mid}")
        else:
            errors += 1
            print(f"Failed to update {mid} - server may not support PATCH/PUT at this endpoint", file=sys.stderr)

    print(f"Done. Processed={processed} Updated={updated} Errors={errors}")


if __name__ == '__main__':
    main()
