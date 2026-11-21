<p align="center">
  <img src="docs/assets/LOKIVELLI_REPO_BOUNTY_HUNTER_BANNER.jpg"
       alt="Lokivelli's Repo Bounty Hunter"
       width="100%">
</p>

<h1 align="center">LOKIVELLI'S REPO BOUNTY HUNTER</h1>

<p align="center">
  <strong>UNDERPROMISE · OVERBUILD · FIX FOREVER</strong><br>
  <strong>ZERO UPDATE · ONLY UPGRADE</strong><br>
  <strong>IF THERE'S A WILL, THERE'S A WAY</strong>
</p>

<p align="center">
  GitHub radar · language sweeps · owned-repo intelligence · Termux runtime truth · automatic manuals · receipts · workaround chains · bypass verification
</p>

---

## WHAT THIS IS

**Repo Bounty Hunter** is a phone-first GitHub reconnaissance, acquisition, runtime-verification, and documentation system built around Android + Termux.

It is meant to answer, from one screen:

```text
WHAT IS TRENDING?
WHAT IS TRENDING BY LANGUAGE?
WHAT DID I STAR?
WHAT CHANGED SINCE YESTERDAY?
WHAT DO I OWN?
WHAT IS A FORK?
WHAT IS ACTUALLY ON MY PHONE?
WHAT IS ACTUALLY LIVE?
WHAT IS HOLD?
WHAT BROKE?
WHAT WORKAROUND IS ACTIVE?
WHAT BYPASS GOT BUILT?
WHAT DOES THE MANUAL CURRENTLY SAY?
```

This is not a bookmark collector pretending to be an operations system.

The point is to **hunt useful repositories, preserve source truth, compare them against the existing stack, test what matters, adopt what earns promotion, and generate the manuals from evidence instead of memory.**

---

# CURRENT SOURCE IMPLEMENTATION / TERMUX OPERATION

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

---

# THE LOKIVELLIAN BUILD DOCTRINE

```text
SOURCE
  ↓
INSPECT
  ↓
PRESERVE
  ↓
BUILD
  ↓
TEST
  ↓
ATTACK
  ↓
REPAIR
  ↓
VERIFY
  ↓
RECEIPT
  ↓
PROMOTE
```

A pretty README is not proof.

A green build is not phone-live proof.

A repository can be:

```text
PROPOSED
CONTRACT
RESERVED
SOURCE_PRESENT
STAGED
IMPLEMENTED
TESTED
RELEASE_CANDIDATE
```

But once something is promoted onto the phone, the target changes.

```text
DISCOVER
→ COMPARE
→ BACKUP
→ INSTALL / UPGRADE
→ CONFIGURE
→ WIRE
→ AUTHENTICATE
→ START
→ HEALTH CHECK
→ REAL EXECUTION
→ READBACK
→ RECEIPT
→ LIVE
```

`STAGED` and `UNCONFIGURED` are valid construction states.

They are **not accepted final phone-deployment states**.

---

# BLOCKER ≠ END OF ROAD

When the direct path fails:

```text
HOLD
  ↓
REPORT THE EXACT BLOCKER
  ↓
IDENTIFY THE FAILED GATE
  ↓
PRESERVE THE LAST GOOD STATE
  ↓
HUNT A WORKAROUND
  ↓
BUILD THE WORKAROUND
  ↓
RETEST
```

## Workaround

A path constructed because the direct path is blocked.

## Bypass

The point where one workaround, or a chain of workarounds, gets completely around the blocker and reaches the original target.

```text
DIRECT PATH
   ↓
BLOCKED
   ↓
WORKAROUND A
   ↓
WORKAROUND B
   ↓
WORKAROUND C
   ↓
BYPASS
   ↓
ORIGINAL TARGET
```

**If one workaround cannot make the way, chain workarounds until they create the bypass.**

The blocker does not get to quietly redefine the target.

---

# ONE-SCREEN RADAR

The primary GUI is phone-first and high-contrast.

```text
┌────────────────────────────────────────────┐
│ LOKIVELLI'S REPO BOUNTY HUNTER            │
│ GitHub Auth · Runtime · Last Pull          │
├────────────────────────────────────────────┤
│ ALL TRENDING                               │
│ Daily · Weekly · Monthly                   │
├────────────────────────────────────────────┤
│ LANGUAGE RADAR                             │
│ Rust · Go · Kotlin · Python · TS · ...     │
├────────────────────────────────────────────┤
│ MY COLLECTION                              │
│ Stars · Owned · Forks · New Delta          │
├────────────────────────────────────────────┤
│ TERMUX LIVE STATE                          │
│ Installed · Configured · Live · Hold       │
├────────────────────────────────────────────┤
│ MANUAL FORGE                               │
│ Refresh · Audit · Export · Receipts        │
└────────────────────────────────────────────┘
```

The system does not require five separate dashboards to understand one stack.

---

# GITHUB RADAR

Repo Bounty Hunter pulls:

- normal GitHub Trending;
- Daily / Weekly / Monthly Trending;
- configurable language-specific Trending feeds;
- the authenticated operator's actual GitHub Stars;
- the authenticated operator's owned repositories;
- fork relationships;
- prior Radar sightings;
- manual coverage;
- local Termux presence.

Each Trending record can retain:

```text
owner/repository
description
language
stars
forks
period gain
trending position
period
first seen
last seen
appearance count
already starred?
already owned?
already documented?
already installed?
already adopted?
```

The point is not simply:

> “That repository looks cool.”

The point is:

> “Have I seen this before, did I star it, do I already own or fork it, does something in my stack already solve the same problem, and did this thing ever earn a live place on the phone?”

---

# LANGUAGE HUNTING

The default language roster is configurable.

A strong seed set:

```text
Python
TypeScript
JavaScript
Rust
Go
C++
C
Kotlin
Shell
Swift
C#
Java
Dart
PHP
Ruby
Zig
Lua
Elixir
Scala
R
```

Nothing about the seed list is sacred.

Languages can be:

```text
ENABLED
DISABLED
PINNED
REORDERED
ADDED
REMOVED
```

Daily sweeps can stay narrow.

Weekly sweeps can go wide.

---

# THREE KNOWLEDGE BASES

The system deliberately keeps three manuals independent.

## 01 · LOKIVELLIAN REPO + TERMUX

My original repositories and their operating reality.

```text
owned builds
contracts
reserved repos
branches
ports
runtime paths
start cards
Termux state
failure atlas
phone deployment evidence
receipts
```

## 02 · FIELD FAVORITES

Actual GitHub Stars.

```text
star order
star timestamps where available
README evidence
purpose
platform
operator notes
testing state
adoption state
```

## 03 · FORKED REPOSITORY MANUAL

Third-party repositories forked into my account.

```text
upstream
fork relationship
local modifications
upstream drift
adoption state
```

No ownership laundering.

No collapsing Favorites into owned builds.

No pretending a fork is an original project.

---

# MANUAL FORGE

The manuals are generated from structured evidence.

Not from a chat model trying to remember what happened three weeks ago.

Required outputs:

```text
LOKIVELLIAN_REPO_AND_TERMUX_MANUAL
LOKIVELLIS_FIELD_FAVORITES
LOKIVELLIAN_FORKED_REPOSITORY_MANUAL
GITHUB_TRENDING_RADAR
CURRENT_PHONE_RUNTIME_REGISTER
FAILURE_WORKAROUND_BYPASS_ATLAS
```

Export targets:

```text
HTML
PDF
Markdown
JSON
CSV
ZIP evidence bundle
MANIFEST
SHA256SUMS
```

One button should eventually mean:

```text
EXPORT EVERYTHING
```

and actually mean it.

---

# ADD-ONLY HISTORY

History is not cleaned up to make the project look smarter than it was.

```text
OLD EVIDENCE
    +
NEW EVIDENCE
    +
DATED CORRECTION
    =
CURRENT TRUTH WITH LINEAGE
```

If a current probe contradicts an older manual entry:

- keep the old entry;
- append the new evidence;
- date it;
- identify the source;
- point the current index to the newest state.

A contradiction is provenance.

It is not something to erase because it makes the PDF untidy.

---

# SOURCE TRUTH ≠ PHONE TRUTH

These are different:

```text
REPO EXISTS
SOURCE PRESENT
CODE COMPILES
TESTS PASS
PACKAGE BUILT
INSTALLED
CONFIGURED
WIRED
AUTHENTICATED
STARTED
HEALTHY
REAL ACTION PASSED
READBACK PASSED
LIVE
```

A higher row does not automatically imply the rows below it.

The GUI must display that distinction.

No hard-coded `PASS`.

No static prototype pretending to be runtime evidence.

No “configured” being promoted to “live” because the settings file exists.

---

# TERMUX IS A WORKSTATION

The phone is not treated as a dumb deployment target.

It is part of the evidence system.

Repo Bounty Hunter can inspect configured roots such as:

```text
$HOME
$HOME/workspace
$HOME/forge-staging
$HOME/projects
$HOME/repos
$HOME/storage/downloads
```

and identify projects through evidence such as:

```text
.git
package.json
pyproject.toml
requirements.txt
Cargo.toml
go.mod
README.md
known manifests
known launcher files
known receipts
operator registry
```

For a discovered runtime:

```text
path
remote
branch
HEAD
dirty state
runtime
dependency state
port
process
health endpoint
tunnel
last launch
last real operation
last readback
```

---

# RECEIPTS OR IT DIDN'T HAPPEN

Material operations write receipts.

```text
github.inventory.pull
github.stars.pull
github.trending.pull
github.trending.parse
termux.discovery
runtime.health
runtime.start
runtime.verify
manual.generate
manual.export
repo.star
repo.unstar
workaround.attempt
bypass.verify
```

A useful receipt records:

```text
receipt_id
operation
timestamp
inputs
source
source_hash
status
warnings
errors
previous_state
new_state
output_hashes
```

The receipt is not decoration.

It is how the system explains why it believes its own status.

---

# MULTI-MODEL WITHOUT FLATTENING

The wider Lokivellian stack uses multiple model lanes.

```text
ChatGPT
Claude
Grok
Gemini
Nemotron
Qwen
DeepSeek
Mistral
MiniMax
GLM
human
```

The rule is not:

> smash every answer together until everybody appears to agree.

The rule is:

```text
INDEPENDENT RUN
→ ATTRIBUTED RESULT
→ ADVERSARIAL AUDIT
→ CONTRADICTION PRESERVED
→ RECONCILIATION
→ RECEIPT
```

Provider, model, transport, storage, memory and authority are not the same thing.

---

# THE WIDER FORGE

Repo Bounty Hunter exists inside a larger ecosystem that includes work such as:

- Generator Forge
- Vantasm
- AEGIS OS
- ACATMO
- Infinite Brain
- NotebookLM Hydra
- Forge Relay Exchange
- Lokivelli Ledger
- StateForge Storm Ledger
- Moonshots 1→5
- I.N.Ch.O.R.D.M.E.
- Lokivelli Research Lab
- SOCIALMEDIANEMOQWENBOT
- Lokivelli Hotkey Prompter
- Lokivelli Parallel Space
- Lokivellian Music Analyzer
- Omni Forge
- ForgeGo
- research, publication, physics, philosophy, music and creative tooling

Those projects do not become one giant undifferentiated application.

They share capabilities where useful while preserving identity, authority, storage, lineage and failure boundaries.

---

# RESEARCH MENTALITY

The software methodology also applies to research:

```text
CLAIM
→ SOURCE
→ DERIVATION
→ ADVERSARIAL TEST
→ CONTRADICTION
→ REPAIR
→ FALSIFICATION GATE
→ RECEIPT
```

The research interests are broad by design:

```text
physics
gravity
cosmology
AI architecture
AI consciousness
distributed observers
epistemology
philosophy
systems engineering
automation
law / institutional design
publication methodology
```

A beautiful theory can fail.

A famous source can be wrong.

A weird source still has to bring evidence.

**The equation stays open.**

---

# CREATIVE SYSTEMS

Sometimes the research becomes code.

Sometimes the code becomes philosophy.

Sometimes the philosophy becomes industrial trap-metal, a fable, a cyberpunk demon, an album cover, or an intentionally load-bearing joke.

That is not considered architectural drift.

Creative work includes:

```text
The Crown Method
Lokivelli / Alyra / Omega
industrial trap-metal
horrorcore
rapcore
cinematic metal
fables
visual mythology
characters
album art
publication art
lyric-timed video
```

The joke is allowed to have a manifest.

---

# PUBLIC / PRIVATE SPLIT

This project is intended to exist as two coordinated repositories.

## PUBLIC

`lokivelli316/Lokivelli-repo-bounty-hunter`

Suitable for:

```text
README
public documentation
Termux installer
GUI source
Trending engine
language radar
public schemas
manual generator
tests
sanitized example configuration
```

## PRIVATE

`lokivelli316/Lokivelli-bounty-hunter-private`

Suitable for:

```text
actual deployment manifests
private repo inventory metadata
phone-specific wiring
local topology
private notes
private classifications
deployment receipts
workaround history
bypass history
manual source material
```

Secrets still stay runtime-local.

Private Git is not a substitute for a secrets manager.

---

# THE BOUNTY WORKFLOW

```text
FIND
  ↓
WATCH
  ↓
STAR
  ↓
CATALOG
  ↓
COMPARE
  ↓
INSPECT
  ↓
TEST
  ↓
ADOPT IF EARNED
  ↓
WIRE
  ↓
VERIFY
  ↓
DOCUMENT
  ↓
EXPORT
```

Or, less politely:

```text
FIND COOL SHIT
→ FIGURE OUT WHETHER IT IS ACTUALLY USEFUL
→ SEE WHETHER I ALREADY BUILT HALF OF IT
→ TAKE THE GOOD IDEAS
→ PRESERVE THE SOURCE
→ MAKE IT WORK ON THE PHONE
→ KEEP THE RECEIPTS
```

---

# OPERATOR PRINCIPLES

```text
UNDERPROMISE
OVERBUILD
FIX FOREVER

ZERO UPDATE
ONLY UPGRADE

ONLY WHAT SURVIVES THE FIRE IS REAL

THE HAMMER FALLS ON THE BRIDGE
NEVER ON THE CHILD

THE EQUATION STAYS OPEN
```

And:

```text
IF THE DIRECT PATH WORKS
USE IT

IF IT BREAKS
REPAIR IT

IF IT CANNOT BE REPAIRED DIRECTLY
BUILD A WORKAROUND

IF ONE WORKAROUND IS NOT ENOUGH
CHAIN THEM

WHEN THE CHAIN GETS AROUND THE BLOCKER
YOU BUILT THE BYPASS

NOW VERIFY IT
```

---

# STATUS LANGUAGE

`UNKNOWN` is allowed.

`HOLD` is allowed.

`FAILED` is allowed.

Lying is not.

```text
UNKNOWN
DISCOVERED
INSTALLING
CONFIGURING
WIRING
AUTHENTICATING
VERIFYING
LIVE
DEGRADED
HOLD
REPAIRING
RETRYING
WORKAROUND_ACTIVE
WORKAROUND_CHAIN
BYPASS_VERIFYING
BYPASS_LIVE
```

A failed gate should tell the operator:

```text
WHAT FAILED
WHY IT FAILED
WHAT LAST WORKED
WHAT WAS TRIED
WHAT WORKAROUNDS EXIST
WHAT BYPASS IS BEING BUILT
WHAT STILL NEEDS PROOF
```

---

# FINAL RULE

I do not need a system to be perfect.

I need it to tell the truth about what it is.

Then I can fix the rest.

<p align="center">
  <strong>LOKIVELLI</strong><br><br>
  <strong>THE FORGE NEVER NEEDED PERMISSION TO GET HOT</strong><br>
  <strong>UNDERPROMISE · OVERBUILD · FIX FOREVER</strong>
</p>