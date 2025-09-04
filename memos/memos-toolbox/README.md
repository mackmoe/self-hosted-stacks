# Self-Hosted Memos

This folder contains scripts to manage Markdown files in the `memos_ready/` directory to a self-hosted Memos instance (see the Memos project: https://github.com/usememos/memos).

## TLDR;4RELZ

Activate the virtualenv from '/home/monash/Git/handy_scripts' then run the scripts from inside the env.

Notes about the virtualenv and project env file
- If you activate the project venv via `source ../venv/bin/activate` the activate script will look for a project env file next to the project (checked in order): `./.venv_env` then `./.env`.
- If no env file exists and you activate interactively, the activate script will offer to create the env file for you and will prompt for `MEMOS_BASE_URL` and `MEMOS_TOKEN`. The token prompt hides input. The file is written with restrictive permissions (600) and sourced automatically when created.
- For security, avoid committing `.venv_env` to git. Consider adding it to `.gitignore`.

## What this repo contains

- `post-2-memos.py` — Main Python script: reads `.md` files from `memos_ready/` and posts them to the Memos API.
- `post-2-memos.sh` — Legacy shell version using `curl` (kept for reference).
- `export-memos.py` — Export all memos from the server to markdown files in `memos_ready/` directory.
- `delete-memos.py` — Delete memos from the server based on tags, date ranges, or interactive selection.
- `cleanup_tags.py` — Helper to find memos with given tags and remove those tags from metadata (dry-run by default; use `--apply` to make changes).
- `memos_ready/` — Place your `.md` files here; each file becomes one memo.

## Requirements

- Python 3
- `requests` package (install with `pip install requests`)
- Running Memos instance and a valid API token

Additionally, this repo lists `types-requests` in `requirements.txt` for improved type hints.

### Usage for `self_hosted-memos/post-2-memos.py`

1. Install dependencies and export a valid `MEMOS_TOKEN`.
2. Add `.md` files to `memos_ready/`.
3. Preview (dry-run):

```bash
python3 post-2-memos.py
```

4. To actually post:

```bash
export MEMOS_DRY_RUN=0
python3 post-2-memos.py
```

### Usage for `export-memos.py`

This script exports all memos from your Memos server to markdown files in the `memos_ready/` directory.

1. Preview what would be exported (dry-run):

```bash
python3 export-memos.py --dry-run
```

2. Export all memos to the default directory:

```bash
python3 export-memos.py
```

3. Export to a custom directory:

```bash
python3 export-memos.py -o /path/to/custom/directory
```

4. Export without metadata comments:

```bash
python3 export-memos.py --no-metadata
```

**Features:**
- Automatically creates safe filenames from memo content
- Handles filename conflicts by adding numbered suffixes
- Includes metadata (memo ID, creation time, visibility) as HTML comments
- Supports pagination to handle large numbers of memos
- Dry-run mode to preview exports without writing files

### Usage for `delete-memos.py`

Before running the deletion script, ensure your environment variables are set (see Environment variable Overrides above).

1. Preview deletion (dry-run mode is enabled by default):

    ```bash
    python3 delete-memos.py
    ```

2. To actually delete memos, disable dry-run by setting:

    ```bash
    export MEMOS_DRY_RUN=0
    python3 delete-memos.py
    ```

Review the list of memos to be deleted carefully before applying changes.

### Usage for `cleanup_tags.py`

This script helps identify memos with specified tags and remove those tags from their metadata. It runs in dry-run mode by default, so it only displays what would be changed.

1. Preview changes with:

    ```bash
    python3 cleanup_tags.py --tags "tag1,tag2"
    ```

    Replace "tag1,tag2" with a comma-separated list of tags to remove.

2. To apply the changes, run:

    ```bash
    python3 cleanup_tags.py --tags "tag1,tag2" --apply
    ```

    This will update the memos after verifying the dry-run output.

Make sure to review the changes before applying them.

## Environment variable Overrides

- `MEMOS_BASE_URL` (optional): Base URL of your Memos instance. Defaults to `http://127.0.0.1:5230` in the script.
- `MEMOS_TOKEN` (required): API token used for Bearer auth.
- `MEMOS_DIR` (optional): Directory containing `.md` files. Defaults to `memos_ready` next to `post-2-memos.py`.
- `MEMOS_VISIBILITY` (optional): Visibility to send. Accepts `public|protected|private` (case-insensitive) or a numeric value. The script normalizes common names (e.g. `public` → server-expected value).
- `MEMOS_DRY_RUN` (optional): By default the script prints payloads and does not POST. Set to `0` or `false` to perform actual POST requests.