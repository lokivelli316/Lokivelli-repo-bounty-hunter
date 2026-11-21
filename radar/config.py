from __future__ import annotations
import json, os
from pathlib import Path

APP_HOME = Path(os.environ.get("LOKIVELLI_RADAR_HOME", "~/lokivelli-radar")).expanduser()
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "default.json"

DIRS = [
    "app", "config", "db", "evidence/github", "evidence/trending", "evidence/termux",
    "evidence/receipts", "manuals/owned-termux", "manuals/favorites", "manuals/forks",
    "manuals/trending", "manuals/runtime", "manuals/failure-atlas", "exports", "backups", "logs", "bin",
    "preservation/mirrors", "preservation/bundles", "preservation/releases", "preservation/wiki"
]

def ensure_layout(home: Path = APP_HOME) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    for rel in DIRS:
        (home / rel).mkdir(parents=True, exist_ok=True)
    cfg = home / "config" / "config.json"
    if not cfg.exists():
        cfg.write_text(DEFAULT_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    return home

def load_config(home: Path = APP_HOME) -> dict:
    ensure_layout(home)
    cfg = json.loads((home / "config" / "config.json").read_text(encoding="utf-8"))
    cfg["termux_roots"] = [os.path.expandvars(os.path.expanduser(x)) for x in cfg.get("termux_roots", [])]
    return cfg

def save_config(cfg: dict, home: Path = APP_HOME) -> None:
    ensure_layout(home)
    tmp = home / "config" / "config.json.tmp"
    target = home / "config" / "config.json"
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, target)
