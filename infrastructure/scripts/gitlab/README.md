# GitLab Repository Restoration & Verification

Tools to reconcile every git repo under `C:\Users\deepak\` against a self-hosted
GitLab instance (`http://localhost:8929`). Reports what is present, what is
missing, what is orphaned, and (opt-in) recreates + pushes anything that was
lost on the GitLab side.

**Repository-safe by design.**

- Read-only by default (`--dry-run` is the default mode).
- Never deletes anything on GitLab.
- Never uses `git push --force`.
- Never logs or prints the PAT.
- Refuses to push dirty working trees unless you explicitly opt in.

---

## 0. Prerequisites

| Requirement                                     | How to verify                                                  |
| ----------------------------------------------- | -------------------------------------------------------------- |
| GitLab CE up at `http://localhost:8929`         | `curl -sSf http://localhost:8929/-/health && echo ok`          |
| PAT with scopes `api` + `write_repository`      | GitLab UI -> User -> Preferences -> Access Tokens              |
| `GITLAB_TOKEN` exported in the current shell    | `printenv GITLAB_TOKEN >/dev/null && echo "token set"` (never `echo $GITLAB_TOKEN`) |
| Python 3.9+                                     | `python --version`                                             |
| `httpx` on PYTHONPATH                           | `python -c "import httpx; print(httpx.__version__)"`           |
| `git` on PATH                                   | `git --version`                                                |
| `jq` (optional, pretty-print inventory)         | `jq --version`                                                 |
| bash 4+ (Git-Bash on Windows or WSL2)           | `bash --version`                                               |

Create the PAT:

1. Go to `http://localhost:8929/-/user_settings/personal_access_tokens`.
2. Name: `reconcile-tool`. Expiration: 7 days.
3. Scopes: `api`, `write_repository`.
4. Export: `export GITLAB_TOKEN='glpat-...'` (in a shell that does NOT write
   history to disk, e.g. `HISTFILE=/dev/null bash`).
5. Confirm: `curl -sSf -H "PRIVATE-TOKEN: $GITLAB_TOKEN" http://localhost:8929/api/v4/user | jq .username`.

Retrieve the root password only if you need to mint a PAT and none exists:

```bash
# Vault path: secret/devops/gitlab/root
vault kv get -field=password secret/devops/gitlab/root
```

Never use the root password with this tool.

---

## 1. Discover local repos

```bash
cd /c/Users/deepak/ai-folder

# Default root is /c/Users/deepak (override with the first positional arg or
# the WORKSPACE_ROOT env var).
./scripts/gitlab/discover_local_repos.sh > scripts/gitlab/inventory.json
```

What you get: a JSON array where each entry looks like

```json
{
  "path": "/c/Users/deepak/ai-folder",
  "remotes": {"origin": "http://localhost:8929/root/ai-folder.git"},
  "default_branch": "master",
  "head": "3da246a",
  "clean": false,
  "uncommitted_files": 42
}
```

Pretty-print with `jq`:

```bash
jq '.[] | {path, origin: .remotes.origin, clean}' scripts/gitlab/inventory.json
```

The script prunes `node_modules`, `.venv`, `dist`, `build`, `target`, `.next`,
`.terraform`, `__pycache__`, `*-data` (chromadb-data, ollama-data, ...) and
similar caches. Adjust `PRUNE_NAMES` in the script if your tree has other
noise. First scan over a large tree can take tens of seconds; re-runs are
fast because everything is in the OS page cache.

Tunables:

- `WORKSPACE_ROOT=/c/Users/deepak/repos ./discover_local_repos.sh`
- `MAX_DEPTH=12 ./discover_local_repos.sh`

---

## 2. Dry-run the reconciliation

```bash
python scripts/gitlab/reconcile.py \
  --inventory scripts/gitlab/inventory.json \
  --gitlab http://localhost:8929 \
  --token "$GITLAB_TOKEN" \
  --dry-run \
  --json-report scripts/gitlab/report.json
```

This only READS from GitLab. It never creates a project, pushes, or deletes.

### What the tool checks

| Bucket              | Definition                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------------------------- |
| `MATCHED`           | Local `origin` URL resolves to a GitLab project that exists under the authenticated user's namespace.         |
| `MISSING_ON_GITLAB` | Local `origin` URL points at this GitLab host but the project returns 404 from the API.                       |
| `ORPHAN_ON_GITLAB`  | Project exists on GitLab but no local clone under the workspace has its URL as origin.                        |
| `LOCAL_ONLY`        | Local repo has no origin, or origin points at a non-GitLab host (GitHub, Gitea, ...).                         |

---

## 3. Review

Read `scripts/gitlab/report.json` (or re-run with `-v` for a debug stream).

Typical decisions:

- `MATCHED` and `clean: true` -> nothing to do.
- `MATCHED` and `clean: false` -> your local has uncommitted work; commit or
  stash before pushing anywhere.
- `MISSING_ON_GITLAB` -> the interesting bucket. Triage:
  - Repo you genuinely care about -> go to step 4.
  - Obsolete experiment -> leave alone, or remove the origin remote locally
    (`git remote remove origin`).
- `ORPHAN_ON_GITLAB` -> GitLab has something you never cloned back. Either
  clone it (`git clone http://localhost:8929/<pwn>.git`) or leave it.
- `LOCAL_ONLY` -> lives elsewhere (GitHub, Gitea). Not this tool's concern.

---

## 4. Restore missing projects

```bash
# Interactive: prompts once with the exact list.
python scripts/gitlab/reconcile.py \
  --inventory scripts/gitlab/inventory.json \
  --gitlab http://localhost:8929 \
  --token "$GITLAB_TOKEN" \
  --push-missing
```

Or fully non-interactive (CI-friendly):

```bash
python scripts/gitlab/reconcile.py \
  --inventory scripts/gitlab/inventory.json \
  --gitlab http://localhost:8929 \
  --token "$GITLAB_TOKEN" \
  --push-missing --yes
```

Per missing repo the tool will:

1. `POST /api/v4/projects` with:
   - `name = path = <project segment of expected path_with_namespace>`
   - `namespace_id = <authenticated user's namespace>`
   - `visibility = private`
   - `default_branch = <local HEAD branch>`
   - `initialize_with_readme = false`
2. `git -C <repo> push origin --all`
3. `git -C <repo> push origin --tags`

Never `--force`. Never `--delete`. Never a different origin URL (the one on
the local repo stays authoritative).

### Dirty trees

The tool skips any local repo whose `clean` is `false`. Override with
`--force-dirty` if you're really sure:

```bash
python scripts/gitlab/reconcile.py ... --push-missing --yes --force-dirty
```

It still never forces the push.

---

## 5. What to expect - sample output

```text
[reconcile] INFO loaded 3 local repos from scripts/gitlab/inventory.json
[reconcile] INFO GitLab base: http://localhost:8929
[reconcile] INFO authenticated as root (user_id=1, namespace_id=1)
[reconcile] INFO enumerated 2 owned GitLab projects
[reconcile] INFO classification: matched=1 missing=1 orphan=1 local_only=1
[reconcile] INFO dry-run mode: no writes performed
========================================================================
GitLab Reconciliation Report
========================================================================
  MATCHED:           1
  MISSING_ON_GITLAB: 1
  ORPHAN_ON_GITLAB:  1
  LOCAL_ONLY:        1
------------------------------------------------------------------------
MATCHED (local <-> GitLab):
  [OK]    /c/Users/deepak/ai-folder
          -> root/ai-folder (id=42, default=master)  [DIRTY uncommitted=42]

MISSING_ON_GITLAB (local origin -> 404 on GitLab):
  [MISS]  /c/Users/deepak/demo-project
          origin=http://localhost:8929/root/demo-project.git expected=root/demo-project branch=main clean=True

ORPHAN_ON_GITLAB (on GitLab but no local clone references it):
  [ORPH]  root/legacy-experiment (id=7, default=main)

LOCAL_ONLY (origin does not point at this GitLab host):
  [LOCL]  /c/Users/deepak/gh-project  (origin does not point at target GitLab host)
========================================================================
```

Exit codes:

- `0` - all good (or dry-run with nothing to do).
- `1` - user aborted the `--push-missing` prompt.
- `2` - input error (bad flags, missing token, malformed inventory).
- `3` - GitLab API auth or enumeration failed.
- `4` - dry-run finished and there are `MISSING_ON_GITLAB` entries.
- `5` - push-missing attempted and at least one action failed.

CI tip: treat exit `4` as a hard fail on scheduled drift-detection runs, and
`0` only when everything is `MATCHED`.

---

## 6. Troubleshooting

### 401 / 403 from GitLab

Your PAT is missing scopes. Required: `api` (everything below) + `write_repository`
(git push over HTTPS). Re-mint at
`http://localhost:8929/-/user_settings/personal_access_tokens`.

### 404 on a project you just pushed

GitLab asynchronously indexes newly-created projects. Re-run `reconcile.py`
~30 seconds later. If still 404, check the project under the authenticated
user's namespace (`root/`), not a group namespace.

### 429 Too Many Requests

The script honors `Retry-After` and backs off up to 5 times with exponential
delay (max 30s). If you're blasting thousands of repos, lower concurrency on
the GitLab side or split the inventory into batches:

```bash
jq '.[0:50]'   inventory.json > batch1.json
jq '.[50:100]' inventory.json > batch2.json
```

### Git push hangs on a large repo

The script does not impose its own timeout on `git push`. If a push for a
multi-GB repo hangs, run the push by hand to see real progress:

```bash
git -C /c/Users/deepak/big-repo push --progress origin --all
git -C /c/Users/deepak/big-repo push --progress origin --tags
```

Then re-run `reconcile.py` - the next pass will classify the project as
`MATCHED` and skip the push step.

### Git LFS

Plain `git push --all` does not automatically push LFS objects. If the repo
uses LFS (`.gitattributes` with `filter=lfs`), push the LFS payload first:

```bash
git -C /c/Users/deepak/lfs-repo lfs install
git -C /c/Users/deepak/lfs-repo lfs push --all origin
git -C /c/Users/deepak/lfs-repo push origin --all
git -C /c/Users/deepak/lfs-repo push origin --tags
```

### Authentication over HTTPS prompts for a password

`git push` against a local GitLab over HTTP(S) authenticates with:

- Username: any (e.g. `oauth2`).
- Password: your PAT.

Easiest, one-shot:

```bash
# Inside the repo, rewrite origin to embed oauth2 + token ONCE, non-persistent:
git -c http.extraHeader="PRIVATE-TOKEN: $GITLAB_TOKEN" \
    -C /c/Users/deepak/demo-project push origin --all
```

A cleaner persistent option is a credential helper:

```bash
git config --global credential.http://localhost:8929.username oauth2
git config --global credential.helper store   # or manager-core on Windows
# First push: type your PAT as the password; it's cached thereafter.
```

Either way, this tool never writes the token into git config on your behalf.

### `GIT_TERMINAL_PROMPT=0` errors

The tool sets `GIT_TERMINAL_PROMPT=0` so pushes that need credentials fail
fast instead of hanging for stdin. If you see
`terminal prompts disabled` in `push_all_branches` errors, set up a
credential helper (previous item) and re-run.

### Origin URL mismatch

The tool compares on host+port (not on the specific http-vs-https scheme).
If you accidentally have `origin = https://localhost:8929/...` while GitLab
is plain HTTP, the reconciliation still works, but `git push` will fail on
certificate validation. Either switch origin to the canonical URL or run
with `GIT_SSL_NO_VERIFY=1` (local-only).

### Inventory entry has the wrong path separator

`discover_local_repos.sh` emits the Git-Bash/WSL view (`/c/Users/...`). If
you're running `reconcile.py` from native Windows Python, `git -C
/c/Users/...` still works because Git for Windows accepts that form. If not,
rewrite paths with `sed`:

```bash
jq '(.[].path) |= sub("^/c/"; "C:/")' inventory.json > inventory.win.json
```

### Submodules

Submodule `.git` directories are skipped because `git -C <submodule>
rev-parse --abbrev-ref HEAD` typically succeeds but the URLs are managed by
the parent `.gitmodules`. Reconcile the parent repo only.

---

## 7. Rollback

The tool is designed so that rollback is rarely needed, but:

| Action                                                | Rollback                                                                                                                            |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `POST /api/v4/projects` created a new empty project   | Delete it from the GitLab UI: `http://localhost:8929/<pwn>/-/edit` -> "Delete project". This tool NEVER does that itself.           |
| `git push origin --all` published history to GitLab   | The tool never uses `--force`, so you never overwrote GitLab history. To un-publish, delete the project (previous row).             |
| `git push origin --tags` published local-only tags    | `git push --delete origin <tagname>` per tag.                                                                                       |
| Credentials got cached by `git config --global`       | `git config --global --unset credential.helper`; delete the entry in Windows Credential Manager (`cmdkey /list` -> `cmdkey /delete`).|
| PAT accidentally printed (it shouldn't)               | Revoke the token immediately at `http://localhost:8929/-/user_settings/personal_access_tokens`, then mint a new one.                |

The inventory file is plain JSON and not secret; feel free to check it into
version control as an audit record.

---

## 8. File map

```
scripts/gitlab/
  discover_local_repos.sh   # bash, writes inventory.json
  reconcile.py              # python, consumes inventory.json + GitLab API
  README.md                 # this file
```
