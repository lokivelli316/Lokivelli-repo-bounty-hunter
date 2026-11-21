# Lokivelli Termux GitHub Radar + Auto-Manual Forge

Deterministic, local-first GitHub/Termux evidence system for Android Termux. The application does not require an AI model for inventory refresh, Trending ingestion, delta calculation, local runtime inspection, manual generation, hashing, receipts, or export.

## Current source implementation

- One-screen high-contrast phone GUI served locally at `http://127.0.0.1:8765`.
- GitHub owned-repository inventory using authenticated pagination with `affiliation=owner`.
- GitHub Stars inventory using authenticated pagination and the star media type so `starred_at` is retained where GitHub returns it.
- Owned originals, owned forks, and starred third-party repositories remain separately classified.
- Owned repository default-branch HEAD enrichment and fork-parent enrichment where the API returns it.
- GitHub Trending HTML-source ingestion for all/daily/weekly/monthly and configurable language lanes.
- Trending source receipts preserve requested URL, HTTP status, parser version, raw HTML SHA-256, raw HTML path, warnings, order, period, and language filter.
- Parser zero-result failures are `HOLD`; they do not become successful empty lists.
- SQLite operational state with append-only receipts and delta events.
- Termux filesystem discovery, git/runtime evidence, process checks, registered health endpoints, and separate source/runtime states.
- Six generated manuals with HTML, PDF, Markdown, JSON, and CSV outputs.
- Append-only manual versions with frozen predecessor import support.
- `EXPORT EVERYTHING` ZIP with `MANIFEST.json`, `SHA256SUMS`, redacted config, data tables, receipts, manuals, and restore support.
- STAR / UNSTAR operations require authenticated GitHub authority and write receipts.
- README audits are stored and searchable; a README command is evidence only and is never converted into an installation state.
- Internal background scheduler supports `manual`, `daily`, `twice_daily`, `weekly`, `monthly`, and 5-field cron-style expressions.
- Update path includes check, compare, backup, fast-forward pull, install, verification, service restart, and rollback state backup.
- Explicit workaround/bypass records preserve the original target, blocker, failed gate, attempt history, workaround chain, bypass point, differences, limitations, rollback path, and verification result.

## Termux installation

```sh
git clone https://github.com/lokivelli316/Lokivelli-repo-bounty-hunter.git
cd Lokivelli-repo-bounty-hunter
bash bin/install-termux.sh
```

The installer creates local application state under `~/lokivelli-radar` by default and installs two Termux `runit` services: the HTTP service and the scheduler.

### GitHub authentication

The token stays local. Supported lookup order is `GITHUB_TOKEN`, `GH_TOKEN`, `~/lokivelli-radar/config/github_token`, then `gh auth token`.

```sh
mkdir -p ~/lokivelli-radar/config
printf '%s' 'YOUR_TOKEN' > ~/lokivelli-radar/config/github_token
chmod 600 ~/lokivelli-radar/config/github_token
```

The exported credential evidence contains state such as `PRESENT` or `MISSING`, not the token value.

## Commands

```sh
lokivelli-radar serve
lokivelli-radar refresh
lokivelli-radar github
lokivelli-radar trending --period daily --language rust
lokivelli-radar sweep
lokivelli-radar discover
lokivelli-radar register-runtime ~/projects/example --port 8080 --health http://127.0.0.1:8080/health
lokivelli-radar manuals
lokivelli-radar export
lokivelli-radar scheduler
lokivelli-radar restore /path/to/LOKIVELLI_RADAR_MANUAL_EXPORT_....zip --home ~/clean-radar
lokivelli-radar import-predecessor owned-termux /path/to/old-manual.pdf
lokivelli-radar update check
lokivelli-radar update backup
lokivelli-radar update verify
lokivelli-radar update apply
lokivelli-radar update rollback --backup-path ~/lokivelli-radar/backups/state-...
```

## Evidence and local data

Default root: `~/lokivelli-radar/`

```text
app/
config/
db/
evidence/github/
evidence/trending/
evidence/termux/
evidence/receipts/
manuals/
exports/
backups/
logs/
bin/
```

Operational state is normalized in SQLite. Material operations write immutable JSON receipts. Generated manual history is additive; current indexes point at the newest generated version without rewriting frozen predecessors.

## Completion status

Source implementation and repository CI are not the same as a completed Samsung/Termux deployment. The build contract requires the entire phone acceptance boundary. Until the application is installed, authenticated, wired, started, health-checked, executed, read back, exported, restored, rollback-tested, and verified on the target phone, deployment status remains **HOLD**, not COMPLETE.
