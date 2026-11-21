from __future__ import annotations
import json, sqlite3
from contextlib import contextmanager
from pathlib import Path
from .config import APP_HOME, ensure_layout
from .receipts import utcnow

SCHEMA = r'''
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS repositories(
  repo_id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL UNIQUE,
  owner TEXT NOT NULL,
  classification TEXT,
  ownership TEXT,
  fork INTEGER NOT NULL DEFAULT 0,
  upstream TEXT,
  visibility TEXT,
  default_branch TEXT,
  current_head TEXT,
  description TEXT,
  primary_language TEXT,
  topics_json TEXT,
  created_at TEXT,
  updated_at TEXT,
  pushed_at TEXT,
  archived INTEGER NOT NULL DEFAULT 0,
  homepage TEXT,
  source_status TEXT,
  phone_status TEXT,
  checkout TEXT,
  documented_install TEXT,
  documented_start TEXT,
  runtime_path TEXT,
  runtime_port INTEGER,
  dependencies_json TEXT,
  platform_requirements_json TEXT,
  credential_state TEXT,
  oauth_state TEXT,
  last_repo_probe TEXT,
  last_phone_probe TEXT,
  last_execution TEXT,
  last_readback TEXT,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stars_current(
  repo_id INTEGER PRIMARY KEY,
  star_position_current INTEGER NOT NULL,
  starred_at TEXT,
  last_seen_in_stars TEXT NOT NULL,
  FOREIGN KEY(repo_id) REFERENCES repositories(repo_id)
);
CREATE TABLE IF NOT EXISTS star_snapshots(
  snapshot_id TEXT NOT NULL,
  repo_id INTEGER NOT NULL,
  position INTEGER NOT NULL,
  starred_at TEXT,
  captured_at TEXT NOT NULL,
  PRIMARY KEY(snapshot_id, repo_id)
);
CREATE TABLE IF NOT EXISTS trending_snapshots(
  snapshot_id TEXT NOT NULL,
  period TEXT NOT NULL,
  language_filter TEXT NOT NULL DEFAULT '',
  position INTEGER NOT NULL,
  repo_id INTEGER,
  full_name TEXT NOT NULL,
  description TEXT,
  primary_language TEXT,
  total_stars INTEGER,
  forks INTEGER,
  period_gain INTEGER,
  captured_at TEXT NOT NULL,
  requested_url TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  stale INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(snapshot_id, position)
);
CREATE INDEX IF NOT EXISTS idx_trending_repo ON trending_snapshots(full_name, captured_at);
CREATE TABLE IF NOT EXISTS trending_sources(
  snapshot_id TEXT PRIMARY KEY,
  requested_url TEXT NOT NULL,
  http_status INTEGER,
  period TEXT NOT NULL,
  language_filter TEXT NOT NULL DEFAULT '',
  captured_at TEXT NOT NULL,
  raw_html_hash TEXT,
  parser_version TEXT,
  parse_warnings_json TEXT,
  status TEXT NOT NULL,
  error TEXT,
  raw_path TEXT,
  repository_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runtime_current(
  path TEXT PRIMARY KEY,
  remote TEXT,
  branch TEXT,
  head TEXT,
  dirty INTEGER,
  runtime_language TEXT,
  build_presence TEXT,
  runtime_port INTEGER,
  process_state TEXT,
  health_endpoint TEXT,
  health_state TEXT,
  service_manager_state TEXT,
  tunnel_state TEXT,
  source_status TEXT,
  phone_status TEXT,
  last_successful_launch TEXT,
  last_verified_operation TEXT,
  probed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  object_key TEXT NOT NULL,
  at TEXT NOT NULL,
  previous_json TEXT,
  current_json TEXT,
  evidence_ref TEXT
);
CREATE TABLE IF NOT EXISTS readme_audits(
  repo_id INTEGER,
  full_name TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  content TEXT,
  findings_json TEXT,
  commands_json TEXT,
  PRIMARY KEY(full_name, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_readme_full_name ON readme_audits(full_name, fetched_at);
CREATE TABLE IF NOT EXISTS notes(
  namespace TEXT NOT NULL,
  object_key TEXT NOT NULL,
  note TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(namespace, object_key)
);
CREATE TABLE IF NOT EXISTS manual_versions(
  manual_key TEXT NOT NULL,
  version_id TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  path TEXT NOT NULL,
  predecessor_ref TEXT,
  evidence_json TEXT,
  PRIMARY KEY(manual_key, version_id)
);
'''

def db_path(home: Path = APP_HOME) -> Path:
    ensure_layout(home)
    return home / "db" / "radar.sqlite3"

@contextmanager
def connect(home: Path = APP_HOME):
    con = sqlite3.connect(db_path(home))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()

def rowdict(row):
    return dict(row) if row is not None else None

def emit_event(con, event_type: str, object_key: str, previous=None, current=None, evidence_ref=None):
    con.execute("INSERT INTO events(event_type,object_key,at,previous_json,current_json,evidence_ref) VALUES(?,?,?,?,?,?)",
                (event_type, object_key, utcnow(), json.dumps(previous, sort_keys=True) if previous is not None else None,
                 json.dumps(current, sort_keys=True) if current is not None else None, evidence_ref))
