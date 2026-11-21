from __future__ import annotations
import hashlib, json, os, secrets
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, ensure_layout

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def write_receipt(operation: str, *, inputs=None, source=None, source_hash=None, result=None,
                  status="OK", warnings=None, errors=None, output_hashes=None,
                  previous_state_ref=None, new_state_ref=None, home: Path = APP_HOME) -> dict:
    ensure_layout(home)
    rid = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{secrets.token_hex(4)}"
    body = {
        "receipt_id": rid,
        "operation": operation,
        "timestamp": utcnow(),
        "inputs": inputs or {},
        "source": source,
        "source_hash": source_hash,
        "result": result or {},
        "status": status,
        "warnings": warnings or [],
        "errors": errors or [],
        "output_hashes": output_hashes or {},
        "previous_state_ref": previous_state_ref,
        "new_state_ref": new_state_ref,
    }
    raw = json.dumps(body, indent=2, sort_keys=True).encode()
    path = home / "evidence" / "receipts" / f"{rid}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    body["receipt_path"] = str(path)
    body["receipt_hash"] = sha256_bytes(raw)
    return body
