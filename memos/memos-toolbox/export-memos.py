#!/usr/bin/env python3

import os
import requests
import sys
import argparse
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    from dateutil import parser as dtp
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False
    dtp = None
    print("Warning: python-dateutil not found. Install with: pip install python-dateutil")
    print("Falling back to basic datetime parsing...")
    import datetime as dt


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


# Try to load .env next to this script only if the variables are not already set
DOTENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
if not os.environ.get("MEMOS_BASE_URL") and not os.environ.get("MEMOS_TOKEN"):
    _load_dotenv(DOTENV_PATH)

# Default configuration
MEMOS_BASE_URL = os.environ.get("MEMOS_BASE_URL", "http://192.168.50.234:5230")
MEMOS_TOKEN = os.environ.get("MEMOS_TOKEN", "")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "memos_ready")

BASE = MEMOS_BASE_URL.rstrip("/")
TOKEN = MEMOS_TOKEN

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
}


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """
    Create a safe filename from memo content.
    Takes the first line, removes markdown formatting, and sanitizes for filesystem.
    """
    if not text:
        return "untitled"
    
    # Get first line only
    first_line = text.split('\n')[0].strip()
    
    # Remove markdown formatting
    first_line = re.sub(r'^#+\s*', '', first_line)  # Remove headers
    first_line = re.sub(r'\*\*(.*?)\*\*', r'\1', first_line)  # Remove bold
    first_line = re.sub(r'\*(.*?)\*', r'\1', first_line)  # Remove italic
    first_line = re.sub(r'`(.*?)`', r'\1', first_line)  # Remove inline code
    first_line = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', first_line)  # Remove links, keep text
    
    # Replace invalid filename characters
    filename = re.sub(r'[<>:"/\\|?*]', '-', first_line)
    filename = re.sub(r'\s+', '-', filename)  # Replace spaces with hyphens
    filename = re.sub(r'-+', '-', filename)  # Remove multiple consecutive hyphens
    filename = filename.strip('-')  # Remove leading/trailing hyphens
    
    # Limit length
    if len(filename) > max_length:
        filename = filename[:max_length].rstrip('-')
    
    # Ensure we have something
    if not filename:
        filename = "untitled"
    
    return filename.lower()


def get_memo_timestamp(memo: Dict[str, Any]) -> str:
    """Get the best available timestamp from a memo."""
    timestamp = memo.get("displayTime") or memo.get("createTime") or ""
    if timestamp:
        try:
            # Parse and format to a nice readable format
            if HAS_DATEUTIL and dtp:
                dt = dtp.isoparse(timestamp)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                # Basic fallback parsing for ISO format
                if 'T' in timestamp:
                    date_part = timestamp.split('T')[0]
                    time_part = timestamp.split('T')[1].split('.')[0] if '.' in timestamp else timestamp.split('T')[1].split('Z')[0]
                    return f"{date_part} {time_part}"
                return timestamp
        except Exception:
            return timestamp
    return ""


def get_memo_id(memo: Dict[str, Any]) -> str:
    """Extract memo ID from name or id field."""
    val = memo.get("name") or memo.get("id") or ""
    return val.split("/")[-1] if val else ""


def list_all_memos() -> List[Dict[str, Any]]:
    """Retrieve all memos from the server using pagination."""
    memos = []
    page_token = ""
    
    print("Fetching memos from server...")
    
    while True:
        url = f"{BASE}/api/v1/memos"
        if page_token:
            url += f"?pageToken={page_token}"
        
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching memos: {e}", file=sys.stderr)
            sys.exit(1)
        
        try:
            data = r.json()
        except json.JSONDecodeError as e:
            print(f"Error parsing response JSON: {e}", file=sys.stderr)
            sys.exit(1)
        
        batch_memos = data.get("memos", [])
        memos.extend(batch_memos)
        
        print(f"Fetched {len(batch_memos)} memos (total: {len(memos)})")
        
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
    
    return memos


def export_memo(memo: Dict[str, Any], output_dir: str, include_metadata: bool = True) -> Optional[str]:
    """
    Export a single memo to a markdown file.
    Returns the filename that was created, or None if failed.
    """
    content = memo.get("content", "")
    if not content:
        print(f"Warning: Memo {get_memo_id(memo)} has no content, skipping")
        return None
    
    # Generate filename
    base_filename = sanitize_filename(content)
    memo_id = get_memo_id(memo)
    timestamp = get_memo_timestamp(memo)
    
    # Create unique filename by adding memo ID if needed
    filename = f"{base_filename}.md"
    full_path = os.path.join(output_dir, filename)
    
    # Handle filename conflicts
    counter = 1
    while os.path.exists(full_path):
        filename = f"{base_filename}-{counter}.md"
        full_path = os.path.join(output_dir, filename)
        counter += 1
    
    # Prepare content for export
    export_content = ""
    
    # Skipping metadata header as per configuration
    
    # Add the actual memo content
    export_content += content
    
    # Ensure content ends with newline
    if not export_content.endswith('\n'):
        export_content += '\n'
    
    # Write to file
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(export_content)
        return filename
    except Exception as e:
        print(f"Error writing file {filename}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Export all memos from Memos server to markdown files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Export all memos to default directory
  %(prog)s -o /path/to/export                 # Export to specific directory
  %(prog)s --no-metadata                      # Export without metadata comments
  %(prog)s --dry-run                          # Show what would be exported without writing files

Environment variables:
  MEMOS_BASE_URL    Base URL of your Memos server (default: http://192.168.50.234:5230)
  MEMOS_TOKEN       API token for authentication
        """
    )
    
    parser.add_argument(
        "-o", "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for exported markdown files (default: {DEFAULT_OUTPUT_DIR})"
    )
    
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Don't include metadata comments in exported files"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be exported without actually writing files"
    )
    
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files instead of creating numbered variants"
    )
    
    args = parser.parse_args()
    
    # Validate configuration
    if not TOKEN:
        print("Error: MEMOS_TOKEN environment variable is required", file=sys.stderr)
        print("Please set your Memos API token in the environment or .env file", file=sys.stderr)
        sys.exit(1)
    
    if not BASE:
        print("Error: MEMOS_BASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    if not args.dry_run:
        os.makedirs(args.output_dir, exist_ok=True)
        print(f"Output directory: {args.output_dir}")
    
    # Fetch all memos
    try:
        memos = list_all_memos()
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    
    if not memos:
        print("No memos found on the server")
        return
    
    print(f"\nFound {len(memos)} memos to export")
    
    # Export each memo
    exported_count = 0
    skipped_count = 0
    
    if args.dry_run:
        print("\nDRY RUN - showing what would be exported:")
        print("-" * 60)
    
    for i, memo in enumerate(memos, 1):
        memo_id = get_memo_id(memo)
        content = memo.get("content", "")
        
        if not content:
            skipped_count += 1
            continue
        
        filename = sanitize_filename(content) + ".md"
        
        if args.dry_run:
            timestamp = get_memo_timestamp(memo)
            preview = content[:100].replace('\n', ' ')
            if len(content) > 100:
                preview += "..."
            print(f"{i:3d}. {filename}")
            print(f"     ID: {memo_id}")
            print(f"     Date: {timestamp}")
            print(f"     Preview: {preview}")
            print()
        else:
            exported_filename = export_memo(memo, args.output_dir, not args.no_metadata)
            if exported_filename:
                print(f"Exported: {exported_filename}")
                exported_count += 1
            else:
                skipped_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"DRY RUN COMPLETE")
        print(f"Would export: {len(memos) - skipped_count} memos")
        print(f"Would skip: {skipped_count} memos (no content)")
    else:
        print(f"EXPORT COMPLETE")
        print(f"Successfully exported: {exported_count} memos")
        print(f"Skipped: {skipped_count} memos (no content or errors)")
        print(f"Files saved to: {args.output_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
