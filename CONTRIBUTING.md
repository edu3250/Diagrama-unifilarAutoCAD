# Contributing to Diagrama-unifilarAutoCAD

Thank you for your interest in contributing! This project follows the **GitFlow** workflow and **Conventional Commits** for clean, traceable development.

## Branch Strategy (GitFlow)

All work is organized into the following branch types:

### Main Branches

- **`main`** — Production-ready releases only
  - Merges only via pull request
  - Each merge must be tagged with a version (e.g., `v0.1.0-docs`)
  - Never commit directly; use a release branch or hotfix

- **`develop`** — Integration branch for the next release
  - Merges feature, release, and hotfix branches
  - Should be deployable or reviewable at all times
  - Feature work targets `develop`

### Supporting Branches

Create supporting branches **from `develop`** (or from `main` for hotfixes):

- **`feature/*`** — New features or enhancements
  - Naming: `feature/vault-scaffold`, `feature/mcp-server-spike`
  - Merge back into `develop` via PR
  - Delete after merge

- **`release/*`** — Preparation for a production release
  - Naming: `release/v0.1.0-docs`
  - Only version bumps, changelog updates, and critical fixes
  - Merge into both `main` (tagged) and back into `develop`
  - Delete after merge

- **`hotfix/*`** — Critical production fixes (from `main` only)
  - Naming: `hotfix/dwg-parser-bug`
  - Merge into both `main` (tagged) and back into `develop`
  - Delete after merge

- **`docs/*`** — Documentation-only changes
  - Naming: `docs/api-reference`, `docs/installation-guide`
  - Merge into `develop`
  - Delete after merge

## Creating a Branch (with or without git-flow)

### If git-flow is available:

```bash
git flow feature start my-feature-name
# or
git flow hotfix start my-fix-name
```

### If using manual branches:

```bash
git checkout develop
git pull origin develop
git checkout -b feature/my-feature-name
# or
git checkout -b docs/my-doc-topic
```

## Commit Messages (Conventional Commits)

All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **`feat`** — A new feature
- **`fix`** — A bug fix
- **`docs`** — Documentation only (changes to .md files, comments)
- **`style`** — Code style (formatting, missing semicolons, etc.)
- **`refactor`** — Code refactoring without feature or fix
- **`perf`** — Performance improvements
- **`test`** — Adding or updating tests
- **`chore`** — Build, CI, or tooling changes (package updates, config)

### Examples

```
feat(vault): add Obsidian sync templates for sources

This commit introduces templated source ingestion to standardize
metadata across all research documents.

Closes #42
```

```
docs(readme): add installation prerequisites section

Clarify Python, Node, and AutoCAD version requirements.
```

```
fix(mcp): handle null response from AutoCAD API

Previously, a missing dispatch ID caused the connector to crash.
Now we validate and return a meaningful error.
```

## Pull Request Workflow

1. **Create a feature branch** from `develop`
2. **Make commits** following Conventional Commits
3. **Keep branch updated** with latest `develop`:
   ```bash
   git fetch origin
   git rebase origin/develop
   ```
4. **Open a PR** targeting `develop` (or `main` for hotfixes)
   - Title: One-line summary (will appear in changelog)
   - Description: Explain *why*, reference issues, describe testing
5. **Request review** from at least one maintainer
6. **Address feedback** — push new commits, do not amend (unless requested)
7. **Merge via PR** after approval — squash commits if requested by reviewer
8. **Delete branch** after merge

## Code Standards

- **Linting** — Code must pass project linters (enforced in CI)
- **Tests** — All new logic must have unit/integration tests
- **Type Hints** — Python and TypeScript code must include type annotations
- **Documentation** — Update relevant `.md` files and docstrings
- **No `console.log` / `print` in production code** — Use proper logging

## Development Setup

The Python package `pvsld` lives in `src/pvsld/` and its tests in `tests/`. Python 3.11 or newer is required.

1. Create and activate a virtual environment in the repository root (`.venv/` is git-ignored):

   ```bash
   python -m venv .venv
   ```

   | Shell | Activate |
   |-------|----------|
   | Windows PowerShell | `.venv\Scripts\Activate.ps1` |
   | Windows cmd | `.venv\Scripts\activate.bat` |
   | Git Bash on Windows | `source .venv/Scripts/activate` |
   | Linux / macOS | `source .venv/bin/activate` |

   If PowerShell refuses to run `Activate.ps1`, allow scripts for the current session only: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

2. Install the package in editable mode together with the development tools (pytest, pytest-cov, ruff):

   ```bash
   pip install -e ".[dev]"
   ```

3. Run the same checks as CI (`.github/workflows/ci.yml`: Ubuntu and Windows, Python 3.11 and 3.12):

   ```bash
   ruff check .             # lint
   ruff format --check .    # formatting; run `ruff format .` to fix
   pytest --cov             # tests; fails below 60 % coverage of pvsld
   ```

### AutoCAD tests

Tests marked `@pytest.mark.autocad` need a licensed local AutoCAD 2027 and only run on Windows. By default, and in CI, they are **skipped** and the skip reason is printed. To run them on the licensed workstation, install the optional `autocad` extra (`pywin32`) and pass the flag:

```bash
pip install -e ".[dev,autocad]"
pytest --run-autocad -m autocad
```

On a platform other than Windows the flag has no effect: the tests stay skipped. New tests that touch AutoCAD must carry the `autocad` marker.

## Testing Before Commit

Run these locally before pushing:

```bash
# Python (see Development Setup)
ruff check .
ruff format --check .
pytest --cov

# Node.js (if applicable)
npm test
npm run lint

# Vault validation (Phase 1)
# (see docs/README.md for vault lint procedures)
```

## Vault Contributions (Phase 1)

Research contributions to the Obsidian vault must:

- Follow the frontmatter conventions in `wiki/CLAUDE.md`
- Use wikilinks (`[[Note Name]]`) for cross-references
- Save raw sources in `.raw/` with a manifest entry
- Never edit `wiki/index.md` or `wiki/log.md` directly; the synthesis step owns those
- Include a summary comment in `wiki/hot.md` if your research is active/recent

See `docs/README.md` for detailed vault structure.

## Release Process

When ready to release a new version:

1. Create a `release/vX.Y.Z` branch from `develop`
2. Update `CHANGELOG.md`, version numbers in code
3. Create a PR into `main`, review, and merge
4. Tag the merge commit: `git tag vX.Y.Z`
5. Push the tag: `git push origin vX.Y.Z`
6. Merge `main` back into `develop` to keep them in sync
7. Delete the release branch

## Questions or Issues?

Open an issue in this repository or contact the maintainer (edu3250@gmail.com).

---

**Last updated:** 2026-10-05
