from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import requests

from .config import APP_HOME, load_config
from .db import connect, emit_event
from .github_client import GitHubClient
from .receipts import sha256_file, utcnow, write_receipt

ACTIONS = {"fork", "private_mirror", "local_mirror", "bundle", "full_archive"}


def _slug(full_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "__", full_name)


def _run(cmd, *, cwd=None, env=None, timeout=1800, check=True):
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(str(x) for x in cmd)} -> {p.returncode}: {(p.stderr or p.stdout)[-1200:]}")
    return p


def _git_env(token: str | None):
    env = os.environ.copy()
    if not token:
        return env, None
    td = tempfile.TemporaryDirectory(prefix="lokivelli-askpass-")
    askpass = Path(td.name) / "askpass.sh"
    askpass.write_text(
        "#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' 'x-access-token' ;; *) printf '%s\\n' \"$LOKIVELLI_GIT_TOKEN\" ;; esac\n",
        encoding="utf-8",
    )
    askpass.chmod(0o700)
    env.update({
        "GIT_ASKPASS": str(askpass),
        "GIT_TERMINAL_PROMPT": "0",
        "LOKIVELLI_GIT_TOKEN": token,
    })
    return env, td


def _roots(home: Path):
    cfg = load_config(home)
    p = cfg.get("preservation", {})
    root = Path(os.path.expandvars(os.path.expanduser(p.get("root", str(home / "preservation")))))
    secondaries = [
        Path(os.path.expandvars(os.path.expanduser(x)))
        for x in p.get("secondary_roots", [])
    ]
    return root, secondaries, p


def _repo_row(full_name: str, home: Path):
    with connect(home) as con:
        row = con.execute("SELECT * FROM repositories WHERE full_name=?", (full_name,)).fetchone()
        if not row:
            return None
        return dict(row)


def set_preservation_plan(full_name: str, actions: list[str], home: Path = APP_HOME):
    wanted = []
    for action in actions:
        action = action.strip().lower()
        if action not in ACTIONS:
            return {"status": "HOLD", "error": f"unknown preservation action: {action}", "valid_actions": sorted(ACTIONS)}
        if action not in wanted:
            wanted.append(action)
    row = _repo_row(full_name, home)
    if not row:
        return {"status": "HOLD", "error": "repository record not found", "full_name": full_name}
    now = utcnow()
    with connect(home) as con:
        previous = con.execute("SELECT * FROM preservation_state WHERE repo_id=?", (row["repo_id"],)).fetchone()
        con.execute(
            """INSERT INTO preservation_state(repo_id,requested_json,status,last_verified_at)
               VALUES(?,?,?,?)
               ON CONFLICT(repo_id) DO UPDATE SET requested_json=excluded.requested_json,status='PLANNED',last_verified_at=excluded.last_verified_at""",
            (row["repo_id"], json.dumps(wanted), "PLANNED", now),
        )
        emit_event(
            con,
            "PRESERVATION PLAN UPDATED",
            full_name,
            dict(previous) if previous else None,
            {"requested": wanted, "status": "PLANNED"},
        )
    receipt = write_receipt(
        "preservation.plan",
        inputs={"full_name": full_name},
        result={"requested": wanted},
        home=home,
    )
    return {"status": "OK", "full_name": full_name, "requested": wanted, "receipt": receipt}


def preservation_status(full_name: str, home: Path = APP_HOME):
    row = _repo_row(full_name, home)
    if not row:
        return {"status": "HOLD", "error": "repository record not found", "full_name": full_name}
    with connect(home) as con:
        state = con.execute("SELECT * FROM preservation_state WHERE repo_id=?", (row["repo_id"],)).fetchone()
    if not state:
        return {"status": "OK", "full_name": full_name, "preservation": None}
    d = dict(state)
    try:
        d["requested"] = json.loads(d.pop("requested_json") or "[]")
    except Exception:
        d["requested"] = []
    try:
        d["verification"] = json.loads(d.pop("verification_json") or "{}")
    except Exception:
        d["verification"] = {}
    return {"status": "OK", "full_name": full_name, "preservation": d}


def _ensure_local_mirror(full_name: str, clone_url: str, token: str | None, mirror_path: Path):
    mirror_path.parent.mkdir(parents=True, exist_ok=True)
    env, td = _git_env(token)
    try:
        if mirror_path.exists():
            _run(["git", "-C", str(mirror_path), "remote", "update"], env=env)
            mode = "updated"
        else:
            _run(["git", "clone", "--mirror", clone_url, str(mirror_path)], env=env)
            mode = "created"
        head = _run(["git", "-C", str(mirror_path), "rev-parse", "HEAD"]).stdout.strip()
        refs = int(_run(["git", "-C", str(mirror_path), "for-each-ref", "--format=%(refname)"]).stdout.count("\n"))
        return {"status": "OK", "mode": mode, "path": str(mirror_path), "head": head, "refs": refs}
    finally:
        if td:
            td.cleanup()


def _bundle(mirror_path: Path, bundle_path: Path):
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = bundle_path.with_suffix(bundle_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    _run(["git", "-C", str(mirror_path), "bundle", "create", str(tmp), "--all"])
    _run(["git", "bundle", "verify", str(tmp)])
    os.replace(tmp, bundle_path)
    return {"status": "OK", "path": str(bundle_path), "sha256": sha256_file(bundle_path), "bytes": bundle_path.stat().st_size}


def _copy_to_secondaries(bundle_path: Path, secondaries: list[Path], slug: str):
    copies = []
    for root in secondaries:
        try:
            root.mkdir(parents=True, exist_ok=True)
            dst = root / f"{slug}.bundle"
            shutil.copy2(bundle_path, dst)
            copies.append({"path": str(dst), "sha256": sha256_file(dst), "status": "OK"})
        except Exception as e:
            copies.append({"path": str(root), "status": "HOLD", "error": str(e)})
    return copies


def _capture_releases(gh: GitHubClient, full_name: str, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    releases = gh.paginate(f"https://api.github.com/repos/{full_name}/releases", params={"per_page": 100})
    metadata = []
    headers = {"Accept": "application/octet-stream", "X-GitHub-Api-Version": "2022-11-28"}
    for rel in releases:
        rmeta = {k: rel.get(k) for k in ("id", "tag_name", "name", "draft", "prerelease", "published_at")}
        rmeta["assets"] = []
        for asset in rel.get("assets") or []:
            name = asset.get("name") or f"asset-{asset.get('id')}"
            target = dest / str(rel.get("id")) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            response = gh._req("GET", asset["url"], headers=headers, allow_redirects=True)
            target.write_bytes(response.content)
            rmeta["assets"].append({"name": name, "bytes": target.stat().st_size, "sha256": sha256_file(target)})
        metadata.append(rmeta)
    meta_path = dest / "releases.json"
    meta_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return {"status": "OK", "count": len(metadata), "path": str(dest), "metadata_sha256": sha256_file(meta_path)}


def _capture_wiki(full_name: str, token: str | None, dest: Path):
    owner, repo = full_name.split("/", 1)
    url = f"https://github.com/{owner}/{repo}.wiki.git"
    env, td = _git_env(token)
    try:
        if dest.exists():
            p = _run(["git", "-C", str(dest), "remote", "update"], env=env, check=False)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            p = _run(["git", "clone", "--mirror", url, str(dest)], env=env, check=False)
        if p.returncode != 0:
            return {"status": "NOT_PRESENT_OR_UNAVAILABLE", "error": (p.stderr or p.stdout)[-800:]}
        return {"status": "OK", "path": str(dest)}
    finally:
        if td:
            td.cleanup()


def _capture_lfs(mirror_path: Path, token: str | None):
    if shutil.which("git-lfs") is None and _run(["git", "lfs", "version"], check=False).returncode != 0:
        return {"status": "UNAVAILABLE", "error": "git-lfs not installed"}
    env, td = _git_env(token)
    try:
        p = _run(["git", "-C", str(mirror_path), "lfs", "fetch", "--all"], env=env, check=False, timeout=3600)
        return {"status": "OK" if p.returncode == 0 else "HOLD", "error": None if p.returncode == 0 else (p.stderr or p.stdout)[-1000:]}
    finally:
        if td:
            td.cleanup()


def _fork(gh: GitHubClient, full_name: str):
    r = gh._req("POST", f"https://api.github.com/repos/{full_name}/forks", json={})
    data = r.json()
    return {"status": "OK", "full_name": data.get("full_name"), "url": data.get("html_url")}


def _private_mirror(gh: GitHubClient, full_name: str, mirror_path: Path, prefix: str):
    user = gh.authenticated_user()
    source_name = full_name.split("/", 1)[1]
    target_name = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{prefix}{source_name}")[:100]
    target_full = f"{user['login']}/{target_name}"
    try:
        detail = gh.repository_detail(target_full)
    except Exception:
        detail = gh._req(
            "POST",
            "https://api.github.com/user/repos",
            json={
                "name": target_name,
                "private": True,
                "description": f"Private preservation mirror of {full_name}",
                "has_issues": False,
                "has_projects": False,
                "has_wiki": False,
            },
        ).json()
    if detail.get("visibility") != "private" and not detail.get("private"):
        raise RuntimeError(f"preservation target {target_full} is not private")
    env, td = _git_env(gh.token)
    try:
        url = f"https://github.com/{target_full}.git"
        p = _run(["git", "-C", str(mirror_path), "push", "--mirror", url], env=env, check=False, timeout=3600)
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout)[-1200:])
    finally:
        if td:
            td.cleanup()
    return {"status": "OK", "full_name": target_full, "url": detail.get("html_url") or f"https://github.com/{target_full}"}


def preserve(full_name: str, actions: list[str] | None = None, home: Path = APP_HOME):
    row = _repo_row(full_name, home)
    if not row:
        return {"status": "HOLD", "error": "repository record not found", "full_name": full_name}

    if actions is None:
        current = preservation_status(full_name, home).get("preservation") or {}
        actions = current.get("requested") or []
    actions = [x.lower() for x in actions]
    unknown = sorted(set(actions) - ACTIONS)
    if unknown:
        return {"status": "HOLD", "error": f"unknown preservation actions: {unknown}", "valid_actions": sorted(ACTIONS)}
    if not actions:
        return {"status": "HOLD", "error": "no preservation actions selected", "full_name": full_name}

    gh = GitHubClient(home)
    root, secondaries, cfg = _roots(home)
    slug = _slug(full_name)
    mirror_path = root / "mirrors" / f"{slug}.git"
    bundle_path = root / "bundles" / f"{slug}.bundle"
    try:
        detail = gh.repository_detail(full_name)
        clone_url = detail.get("clone_url") or f"https://github.com/{full_name}.git"
    except Exception as source_error:
        existing = {
            "mirror": str(mirror_path) if mirror_path.exists() else None,
            "bundle": str(bundle_path) if bundle_path.exists() else None,
            "bundle_sha256": sha256_file(bundle_path) if bundle_path.exists() else None,
        }
        status = "HOLD"
        now = utcnow()
        with connect(home) as con:
            previous = con.execute("SELECT * FROM preservation_state WHERE repo_id=?", (row["repo_id"],)).fetchone()
            con.execute(
                """INSERT INTO preservation_state(repo_id,requested_json,status,mirror_path,bundle_path,last_verified_at,source_present,verification_json)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(repo_id) DO UPDATE SET status=excluded.status,
                     mirror_path=COALESCE(excluded.mirror_path,preservation_state.mirror_path),
                     bundle_path=COALESCE(excluded.bundle_path,preservation_state.bundle_path),
                     last_verified_at=excluded.last_verified_at,source_present=0,verification_json=excluded.verification_json""",
                (
                    row["repo_id"],
                    json.dumps(actions),
                    status,
                    existing["mirror"],
                    existing["bundle"],
                    now,
                    0,
                    json.dumps({"source_error": str(source_error), "existing_recovery": existing}, sort_keys=True),
                ),
            )
            emit_event(
                con,
                "UPSTREAM MISSING / PRESERVED COPY AVAILABLE" if existing["mirror"] or existing["bundle"] else "UPSTREAM MISSING / NO PRESERVED COPY",
                full_name,
                dict(previous) if previous else None,
                {"source_present": False, "existing_recovery": existing},
            )
        receipt = write_receipt(
            "preservation.source_missing",
            inputs={"full_name": full_name, "actions": actions},
            status=status,
            result={"source_present": False, "existing_recovery": existing},
            errors=[str(source_error)],
            home=home,
        )
        return {
            "status": status,
            "full_name": full_name,
            "source_present": False,
            "error": str(source_error),
            "existing_recovery": existing,
            "receipt": receipt,
        }

    results = {}
    errors = []

    needs_local = bool(set(actions) & {"local_mirror", "bundle", "full_archive", "private_mirror"})
    if needs_local:
        try:
            results["local_mirror"] = _ensure_local_mirror(full_name, clone_url, gh.token, mirror_path)
        except Exception as e:
            results["local_mirror"] = {"status": "HOLD", "error": str(e)}
            errors.append(f"local_mirror: {e}")

    if "fork" in actions:
        try:
            results["fork"] = _fork(gh, full_name)
        except Exception as e:
            results["fork"] = {"status": "HOLD", "error": str(e)}
            errors.append(f"fork: {e}")

    if "private_mirror" in actions and results.get("local_mirror", {}).get("status") == "OK":
        try:
            results["private_mirror"] = _private_mirror(
                gh,
                full_name,
                mirror_path,
                cfg.get("private_mirror_prefix", "archive-"),
            )
        except Exception as e:
            results["private_mirror"] = {"status": "HOLD", "error": str(e)}
            errors.append(f"private_mirror: {e}")

    if ("bundle" in actions or "full_archive" in actions) and results.get("local_mirror", {}).get("status") == "OK":
        try:
            results["bundle"] = _bundle(mirror_path, bundle_path)
            results["secondary_copies"] = _copy_to_secondaries(bundle_path, secondaries, slug)
        except Exception as e:
            results["bundle"] = {"status": "HOLD", "error": str(e)}
            errors.append(f"bundle: {e}")

    if "full_archive" in actions and results.get("local_mirror", {}).get("status") == "OK":
        try:
            results["lfs"] = _capture_lfs(mirror_path, gh.token)
            if results["lfs"].get("status") == "HOLD":
                errors.append(f"lfs: {results['lfs'].get('error')}")
        except Exception as e:
            results["lfs"] = {"status": "HOLD", "error": str(e)}
            errors.append(f"lfs: {e}")
        try:
            results["releases"] = _capture_releases(gh, full_name, root / "releases" / slug)
        except Exception as e:
            results["releases"] = {"status": "HOLD", "error": str(e)}
            errors.append(f"releases: {e}")
        try:
            results["wiki"] = _capture_wiki(full_name, gh.token, root / "wiki" / f"{slug}.git")
        except Exception as e:
            results["wiki"] = {"status": "HOLD", "error": str(e)}
            errors.append(f"wiki: {e}")

    now = utcnow()
    verify = {
        "actions": actions,
        "results": results,
        "source_present": True,
        "source_head": detail.get("default_branch"),
    }
    status = "OK" if not errors else "HOLD"
    with connect(home) as con:
        previous = con.execute("SELECT * FROM preservation_state WHERE repo_id=?", (row["repo_id"],)).fetchone()
        con.execute(
            """INSERT INTO preservation_state(
                repo_id,requested_json,status,fork_full_name,private_mirror_full_name,mirror_path,bundle_path,
                upstream_head,last_preserved_at,last_verified_at,source_present,verification_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(repo_id) DO UPDATE SET
                requested_json=excluded.requested_json,status=excluded.status,
                fork_full_name=COALESCE(excluded.fork_full_name,preservation_state.fork_full_name),
                private_mirror_full_name=COALESCE(excluded.private_mirror_full_name,preservation_state.private_mirror_full_name),
                mirror_path=COALESCE(excluded.mirror_path,preservation_state.mirror_path),
                bundle_path=COALESCE(excluded.bundle_path,preservation_state.bundle_path),
                upstream_head=excluded.upstream_head,last_preserved_at=excluded.last_preserved_at,
                last_verified_at=excluded.last_verified_at,source_present=excluded.source_present,
                verification_json=excluded.verification_json""",
            (
                row["repo_id"],
                json.dumps(actions),
                status,
                (results.get("fork") or {}).get("full_name"),
                (results.get("private_mirror") or {}).get("full_name"),
                str(mirror_path) if mirror_path.exists() else None,
                str(bundle_path) if bundle_path.exists() else None,
                (results.get("local_mirror") or {}).get("head"),
                now,
                now,
                1,
                json.dumps(verify, sort_keys=True),
            ),
        )
        emit_event(
            con,
            "PRESERVATION VERIFIED" if status == "OK" else "PRESERVATION HOLD",
            full_name,
            dict(previous) if previous else None,
            {"status": status, "actions": actions, "results": results},
        )
    receipt = write_receipt(
        "preservation.run",
        inputs={"full_name": full_name, "actions": actions},
        source=clone_url,
        status=status,
        result=results,
        errors=errors,
        home=home,
    )
    return {"status": status, "full_name": full_name, "actions": actions, "results": results, "errors": errors, "receipt": receipt}


def preserve_planned(home: Path = APP_HOME):
    plans = []
    with connect(home) as con:
        for row in con.execute(
            """SELECT r.full_name,p.requested_json
               FROM preservation_state p JOIN repositories r ON r.repo_id=p.repo_id
               WHERE p.requested_json IS NOT NULL AND p.requested_json != '[]'
               ORDER BY r.full_name"""
        ):
            plans.append((row["full_name"], json.loads(row["requested_json"] or "[]")))
    results = [preserve(full_name, actions, home) for full_name, actions in plans]
    status = "OK" if all(x.get("status") == "OK" for x in results) else "HOLD"
    receipt = write_receipt("preservation.sweep", status=status, result={"repositories": len(results)}, home=home)
    return {"status": status, "count": len(results), "results": results, "receipt": receipt}
