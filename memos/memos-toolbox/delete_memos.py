#!/usr/bin/env python3

import os, requests, sys, argparse, hashlib, difflib
from collections import defaultdict
from dateutil import parser as dtp


def _load_dotenv(path: str):
    """Lightweight .env loader: set os.environ keys if not already set."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                # Remove surrounding quotes if present
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                # Do not overwrite existing environment variables
                os.environ.setdefault(k, v)
    except FileNotFoundError:
        return


# Try to load .env next to this script only if the variables are not already set in the process environment
DOTENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
if not os.environ.get("MEMOS_BASE_URL") and not os.environ.get("MEMOS_TOKEN"):
    _load_dotenv(DOTENV_PATH)

# default placeholders (can be overridden via environment or .env)
MEMOS_BASE_URL = os.environ.get("MEMOS_BASE_URL", "http://192.168.50.234:5230")
MEMOS_TOKEN = os.environ.get("MEMOS_TOKEN", "")

BASE = MEMOS_BASE_URL.rstrip("/")
TOKEN = MEMOS_TOKEN

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
}

def prompt_inputs(args):
    """Collect TAG, FROM, TO either from args or interactively."""
    tag = args.tag if args.tag is not None else input("Enter tag (without #, leave blank if none): ").strip()
    fr = args.frm if args.frm is not None else input("Enter FROM datetime (ISO8601, leave blank if none): ").strip()
    to = args.to if args.to is not None else input("Enter TO datetime (ISO8601, leave blank if none): ").strip()
    tag = tag.lstrip("#").lower()
    return tag, fr, to

def in_range(iso_time: str, fr: str, to: str) -> bool:
    if not iso_time:
        return False if (fr or to) else True
    t = dtp.isoparse(iso_time)
    if fr and t < dtp.isoparse(fr):
        return False
    if to and t > dtp.isoparse(to):
        return False
    return True

def matches_tag(content: str, tag: str) -> bool:
    if not tag:
        return True
    c = (content or "").lower()
    # match "#tag" or bare "tag" at word boundaries
    return (f"#{tag}" in c) or (f" {tag} " in f" {c} ")

def list_all_memos():
    page_token = ""
    while True:
        url = f"{BASE}/api/v1/memos"
        if page_token:
            url += f"?pageToken={page_token}"
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        for m in data.get("memos", []):
            yield m
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

def memo_id(memo):
    # IDs are often in "name" or "id"; normalize to the trailing segment.
    val = memo.get("name") or memo.get("id") or ""
    return val.split("/")[-1]

def memo_time(memo):
    # Prefer displayTime, else createTime
    return memo.get("displayTime") or memo.get("createTime") or ""

def delete_memo(mid):
    url = f"{BASE}/api/v1/memos/{mid}"
    try:
        r = requests.delete(url, headers=headers, timeout=30)
    except Exception as e:
        print(f"ERR deleting {mid}: request failed: {e}", file=sys.stderr)
        return False
    if r.status_code in (200, 204):
        print(f"Deleted {mid} (status={r.status_code})")
        return True
    # print diagnostic info to help debugging why delete failed
    try:
        body = r.text
    except Exception:
        body = '<unreadable response body>'
    print(f"ERR deleting {mid}: status={r.status_code} url={url}", file=sys.stderr)
    print(f"Response body: {body}", file=sys.stderr)
    return False


def choose_and_delete(memos):
    """List memos and let the user choose one to delete."""
    memos = list(memos)
    if not memos:
        print("No memos matched the query.")
        return
    print("Matched memos:")
    for i, m in enumerate(memos, 1):
        mid = memo_id(m)
        t = memo_time(m)
        snip = (m.get("snippet") or m.get("content", ""))[:80].replace('\n', ' ')
        print(f"{i}. id={mid} time={t} snippet={snip}")
    sel = input("Enter the number or id to delete (blank to cancel): ").strip()
    if not sel:
        print("Cancelled.")
        return
    # resolve selection
    target = None
    if sel.isdigit():
        idx = int(sel) - 1
        if 0 <= idx < len(memos):
            target = memo_id(memos[idx])
    else:
        # assume id
        target = sel
    if not target:
        print("Invalid selection.")
        return
    confirm = input(f"Confirm delete {target}? Type 'yes' to proceed: ")
    if confirm.lower() == 'yes':
        delete_memo(target)
        print(f"Deleted {target}")
    else:
        print("Aborted.")


def _normalize_content_for_hash(s: str) -> str:
    # reduce whitespace, lowercase — keep a lightweight fingerprint
    if not s:
        return ""
    return " ".join(s.split()).lower()


def find_exact_duplicates():
    """Return groups of memos that have identical normalized content.

    Returns a dict: hash -> list[memo]
    """
    groups = defaultdict(list)
    for m in list_all_memos():
        content = m.get('content') or m.get('snippet') or ''
        key = hashlib.sha256(_normalize_content_for_hash(content).encode('utf-8')).hexdigest()
        groups[key].append(m)
    # filter groups with more than one entry
    return {k: v for k, v in groups.items() if len(v) > 1}


def find_similar_duplicates(threshold: float = 0.9):
    """Find groups of memos with similar content using difflib SequenceMatcher.

    This is O(n^2) in number of memos; not suitable for very large collections.
    Returns a list of lists (groups) where each group has >=2 similar memos.
    """
    memos = list(list_all_memos())
    n = len(memos)
    if n < 2:
        return []
    contents = [(_normalize_content_for_hash(m.get('content') or m.get('snippet') or ''), i) for i, m in enumerate(memos)]
    used = [False] * n
    groups = []
    for i in range(n):
        if used[i]:
            continue
        base, _ = contents[i]
        group = [memos[i]]
        used[i] = True
        for j in range(i + 1, n):
            if used[j]:
                continue
            other, _ = contents[j]
            if not base and not other:
                # both empty -> consider duplicate
                sim = 1.0
            else:
                sim = difflib.SequenceMatcher(None, base, other).ratio()
            if sim >= threshold:
                group.append(memos[j])
                used[j] = True
        if len(group) > 1:
            groups.append(group)
    return groups


def show_duplicate_groups(groups):
    total = 0
    for gi, group in enumerate(groups, 1):
        print(f"Group {gi} ({len(group)} items):")
        for m in group:
            mid = memo_id(m)
            t = memo_time(m)
            s = (m.get('snippet') or m.get('content',''))[:120].replace('\n',' ')
            print(f" - id={mid} time={t} snippet={s}")
        total += len(group)
        print("")
    print(f"Found {len(groups)} duplicate groups, {total} memos total.")


def prompt_and_delete_group(group):
    print("Candidates:")
    for i, m in enumerate(group, 1):
        mid = memo_id(m)
        t = memo_time(m)
        s = (m.get('snippet') or m.get('content',''))[:140].replace('\n',' ')
        print(f"{i}. id={mid} time={t} snippet={s}")
    keep = input("Enter the number to KEEP (all others will be deleted). Leave blank to cancel: ").strip()
    if not keep:
        print("Cancelled.")
        return 0
    if not keep.isdigit() or not (1 <= int(keep) <= len(group)):
        print("Invalid selection.")
        return 0
    keep_idx = int(keep) - 1
    deleted = 0
    for i, m in enumerate(group):
        if i == keep_idx:
            continue
        mid = memo_id(m)
        confirm = input(f"Confirm delete {mid}? Type 'yes' to proceed: ")
        if confirm.lower() == 'yes':
            delete_memo(mid)
            deleted += 1
            print(f"Deleted {mid}")
        else:
            print(f"Skipped {mid}")
    return deleted



def delete_everything():
    """Delete all memos in the instance after explicit confirmation."""
    # Snapshot all memo IDs first to avoid pagination issues when deleting while iterating
    print("Collecting memo ids...")
    ids = [memo_id(m) for m in list_all_memos()]
    total = len(ids)
    if total == 0:
        print(f"No memos found on {BASE}.")
        return
    print(f"This will DELETE ALL memos on {BASE} ({total} total).\nThis operation is irreversible.")
    confirm = input("Type DELETE ALL to confirm: ")
    if confirm != 'DELETE ALL':
        print("Confirmation failed; aborting.")
        return
    # perform deletion from snapshot
    deleted = 0
    failed = 0
    for mid in ids:
        ok = delete_memo(mid)
        if ok:
            deleted += 1
        else:
            failed += 1
            print(f"Failed to delete {mid}", file=sys.stderr)
        if deleted > 0 and deleted % 100 == 0:
            print(f"Deleted {deleted}...")
    print(f"Deleted {deleted} memos. Failed: {failed}.")
def list_memos(tag=None, limit=None):
    """Print memos (optionally filtered by tag)."""
    i = 0
    for m in list_all_memos():
        if tag:
            # check tags array and content
            tags = [t.lower() for t in (m.get('tags') or [])]
            content = m.get('content','') or ''
            if tag.lower() not in tags and f"#{tag.lower()}" not in content.lower():
                continue
        i += 1
        mid = memo_id(m)
        t = memo_time(m)
        snip = (m.get('snippet') or m.get('content',''))[:140].replace('\n',' ')
        print(f"{i}. id={mid} time={t} tags={m.get('tags')} snippet={snip}")
        if limit and i >= limit:
            break
    if i == 0:
        print("No memos found.")


def delete_by_id_or_name():
    q = input("Enter memo id or 'memos/<id>' (or leave blank to cancel): ").strip()
    if not q:
        print("Cancelled.")
        return
    # normalize
    mid = q.split('/')[-1]
    confirm = input(f"Confirm delete {mid}? Type 'yes' to proceed: ")
    if confirm.lower() == 'yes':
        delete_memo(mid)
        print(f"Deleted {mid}")
    else:
        print("Aborted.")


def delete_all_with_tag(tag: str):
    tag = tag.lstrip('#').lower()
    matches = []
    for m in list_all_memos():
        tags = [t.lower() for t in (m.get('tags') or [])]
        content = m.get('content','') or ''
        if tag in tags or f"#{tag}" in content.lower():
            matches.append(m)
    if not matches:
        print(f"No memos found with tag '{tag}'.")
        return
    print(f"Found {len(matches)} memos with tag '{tag}':")
    for m in matches[:50]:
        s = (m.get('snippet') or m.get('content',''))[:100].replace('\n',' ')
        print(f" - {memo_id(m)}  time={memo_time(m)}  snippet={s}")
    confirm = input(f"Type 'yes' to DELETE ALL {len(matches)} memos with tag '{tag}': ")
    if confirm.lower() != 'yes':
        print("Aborted.")
        return
    deleted = 0
    for m in matches:
        mid = memo_id(m)
        delete_memo(mid)
        deleted += 1
    print(f"Deleted {deleted} memos with tag '{tag}'.")


def interactive_menu():
    if not TOKEN:
        print("MEMOS_TOKEN is not set in the environment. Set MEMOS_TOKEN and re-run.")
        return
    while True:
        print("\nSelect action:\n 1) List memos\n 2) Delete memo by id/name\n 3) Delete all memos with a tag\n 4) Delete ALL memos (dangerous)\n 5) Quit\n 6) Find exact duplicate memos\n 7) Find similar memos (interactive)")
        cmd = input("Enter number: ").strip()
        if cmd == '1':
            tag = input("Optional tag to filter by (leave blank for all): ").strip()
            list_memos(tag=tag or None)
        elif cmd == '2':
            delete_by_id_or_name()
        elif cmd == '3':
            tag = input("Enter tag to delete (without #): ").strip()
            if tag:
                delete_all_with_tag(tag)
        elif cmd == '4':
            print("WARNING: This will attempt to delete EVERY memo in the instance.")
            confirm = input("Type DELETE ALL to confirm: ")
            if confirm == 'DELETE ALL':
                delete_everything()
            else:
                print("Aborted.")
        elif cmd == '5' or cmd.lower() in ('q','quit','exit'):
            print("Bye")
            break
        elif cmd == '6':
            print("Finding exact duplicate memos...")
            groups = list(find_exact_duplicates().values())
            if not groups:
                print("No exact duplicates found.")
                continue
            show_duplicate_groups(groups)
            for g in groups:
                prompt_and_delete_group(g)
        elif cmd == '7':
            s = input("Enter similarity threshold (0-1, default 0.9): ").strip() or '0.9'
            try:
                thr = float(s)
            except Exception:
                print("Invalid threshold")
                continue
            groups = find_similar_duplicates(threshold=thr)
            if not groups:
                print("No similar groups found.")
                continue
            show_duplicate_groups(groups)
            for g in groups:
                prompt_and_delete_group(g)
        else:
            print("Unknown option")


def main():
    parser = argparse.ArgumentParser(description='Interactive memos deletion tool')
    parser.add_argument('--list', action='store_true', help='List memos and exit')
    parser.add_argument('--tag', help='Filter by tag for list/delete')
    parser.add_argument('--limit', type=int, help='Limit number of listed memos')
    parser.add_argument('--noninteractive-delete', metavar='ID', help='Delete a single memo by id non-interactively')
    parser.add_argument('--find-duplicates', action='store_true', help='Find exact duplicate memos')
    parser.add_argument('--find-similar', type=float, metavar='THRESHOLD', help='Find similar memos with similarity threshold (0-1)')
    parser.add_argument('--auto-delete-duplicates', action='store_true', help="Auto-delete duplicates when found (will prompt per group)")
    parser.add_argument('--interactive', action='store_true', help='Start interactive menu')
    args = parser.parse_args()

    if args.list:
        list_memos(tag=args.tag, limit=args.limit)
        return
    if args.noninteractive_delete:
        mid = args.noninteractive_delete.split('/')[-1]
        delete_memo(mid)
        print(f"Deleted {mid}")
        return
    if args.find_duplicates:
        groups = list(find_exact_duplicates().values())
        if not groups:
            print("No exact duplicates found.")
            return
        show_duplicate_groups(groups)
        if args.auto_delete_duplicates:
            for g in groups:
                prompt_and_delete_group(g)
        return
    if args.find_similar is not None:
        thr = float(args.find_similar)
        if not (0.0 <= thr <= 1.0):
            print("Threshold must be between 0 and 1")
            return
        groups = find_similar_duplicates(threshold=thr)
        if not groups:
            print("No similar groups found.")
            return
        show_duplicate_groups(groups)
        if args.auto_delete_duplicates:
            for g in groups:
                prompt_and_delete_group(g)
        return
    # default: interactive menu
    interactive_menu()


if __name__ == "__main__":
    main()
