from __future__ import annotations
import json, tempfile
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, load_config
from .db import connect
from .receipts import sha256_file, write_receipt, utcnow
from .github_client import pull_inventory, resolve_token
from .trending import sweep
from .termux import discover
from .manuals import MANUALS, generate_all
from .exporter import export_everything, restore_export
from .update import verify_source, migrate_database

PUBLIC_REPO="lokivelli316/Lokivelli-repo-bounty-hunter"
FORMATS=("html","pdf","md","json","csv")
HERO_ASSET="LOKIVELLI_REPO_BOUNTY_HUNTER_LOOP.mp4"

def _receipt_success(home:Path, operations:set[str]):
    found=[]
    receipt_dir=home/"evidence"/"receipts"
    if not receipt_dir.exists():
        return found
    for p in receipt_dir.glob("*.json"):
        try:
            d=json.loads(p.read_text(encoding="utf-8"))
            if d.get("operation") in operations and d.get("status")=="OK":
                found.append(d)
        except Exception:
            pass
    return sorted(found,key=lambda x:x.get("timestamp","") or "",reverse=True)

def _device_flags(home:Path):
    p=home/"config"/"device_acceptance.json"
    if not p.exists():
        return {
            "portrait":False,
            "landscape":False,
            "large_touch_targets":False,
            "no_color_only_status":False,
            "samsung_browser_or_webview":False,
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_device_acceptance(flags:dict,home:Path=APP_HOME):
    allowed={"portrait","landscape","large_touch_targets","no_color_only_status","samsung_browser_or_webview"}
    data={k:bool(flags.get(k)) for k in allowed}
    p=home/"config"/"device_acceptance.json"
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8")
    tmp.replace(p)
    r=write_receipt("device.acceptance.record",result=data,home=home)
    return {"status":"OK","device":data,"receipt":r}

def run_acceptance(home:Path=APP_HOME,source_dir:Path|None=None,network_refresh=True):
    source_dir=source_dir or Path(__file__).resolve().parents[1]
    cfg=load_config(home)
    completed=[]
    failed=[]
    blockers=[]
    details={}

    def gate(name,passed,detail=None,blocker=None):
        passed=bool(passed)
        (completed if passed else failed).append(name)
        details[name]=detail
        if not passed and blocker:
            blockers.append({"gate":name,"blocker":blocker})
        return passed

    token,_=resolve_token(home)
    gate(
        "github.auth.present",
        bool(token),
        {"state":"PRESENT" if token else "MISSING"},
        "GitHub credential is not available to the local Termux application",
    )

    inv=None
    if network_refresh and token:
        inv=pull_inventory(home)
        details["github.inventory.live_refresh"]=inv

    with connect(home) as con:
        owned_db=con.execute("SELECT COUNT(*) FROM repositories WHERE ownership='owned' AND github_present=1").fetchone()[0]
        stars_db=con.execute("SELECT COUNT(*) FROM stars_current").fetchone()[0]
        star_ts=con.execute("SELECT COUNT(*) FROM stars_current WHERE starred_at IS NOT NULL").fetchone()[0]

    if inv:
        gate(
            "github.owned.pagination_and_count",
            inv.get("status")=="OK" and inv.get("owned_count")==owned_db,
            {"api":inv.get("owned_count"),"db":owned_db},
            "Owned repository live inventory did not verify",
        )
        gate(
            "github.stars.pagination_and_count",
            inv.get("status")=="OK" and inv.get("star_count")==stars_db,
            {"api":inv.get("star_count"),"db":stars_db},
            "Star live inventory did not verify",
        )
    else:
        gate(
            "github.owned.pagination_and_count",
            owned_db>0,
            {"db":owned_db},
            "No live inventory refresh was executed and no current owned inventory exists",
        )
        gate(
            "github.stars.pagination_and_count",
            stars_db>=0,
            {"db":stars_db},
            "No current star inventory exists",
        )

    gate(
        "github.star_timestamps",
        stars_db==0 or star_ts==stars_db,
        {"stars":stars_db,"with_timestamp":star_ts},
        "One or more current Stars lack starred_at evidence",
    )
    writes=_receipt_success(home,{"repo.star","repo.unstar"})
    gate(
        "github.star_write_authority",
        bool(writes),
        {"successful_write_receipts":len(writes)},
        "No successful STAR/UNSTAR receipt exists yet; write authority has not been behaviorally verified",
    )

    if network_refresh and token:
        trend=sweep(home,priority_only=False)
        details["trending.live_sweep"]=trend

    with connect(home) as con:
        for period in ("daily","weekly","monthly"):
            src=con.execute(
                "SELECT * FROM trending_sources WHERE period=? AND language_filter='' ORDER BY captured_at DESC LIMIT 1",
                (period,),
            ).fetchone()
            ok=bool(src and src["status"]=="OK" and src["repository_count"]>0)
            gate(
                f"trending.all.{period}",
                ok,
                dict(src) if src else None,
                f"ALL {period} Trending has no successful non-empty verified snapshot",
            )
        for lang in [x for x in cfg.get("languages",[]) if x.get("enabled")]:
            for period in ("daily","weekly","monthly"):
                src=con.execute(
                    "SELECT * FROM trending_sources WHERE period=? AND language_filter=? ORDER BY captured_at DESC LIMIT 1",
                    (period,lang["slug"]),
                ).fetchone()
                ok=bool(src and src["status"]=="OK" and src["repository_count"]>0)
                gate(
                    f"trending.{lang['slug']}.{period}",
                    ok,
                    {"status":src["status"],"count":src["repository_count"]} if src else None,
                    f"Enabled language {lang['slug']} {period} has no successful non-empty verified snapshot",
                )
        source_rows=[dict(r) for r in con.execute("SELECT * FROM trending_sources WHERE status='OK'")]

    hash_fail=[]
    for src in source_rows:
        p=Path(src.get("raw_path") or "")
        if not p.exists() or not src.get("raw_html_hash") or sha256_file(p)!=src["raw_html_hash"]:
            hash_fail.append(src.get("snapshot_id"))
    gate(
        "trending.raw_evidence_hashes",
        not hash_fail,
        {"checked":len(source_rows),"failed":hash_fail},
        "One or more successful Trending snapshots lack matching raw HTML hash evidence",
    )

    index=source_dir/"static"/"index.html"
    wiring=source_dir/"static"/"wiring.js"
    hero=source_dir/"static"/"assets"/HERO_ASSET
    html=index.read_text(encoding="utf-8") if index.exists() else ""
    expected_endpoints=(
        "/healthz",
        "/api/trending",
        "/api/github/inventory",
        "/api/runtime/discover",
        "/api/runtime/health",
        "/api/export/all",
    )
    gate(
        "gui.one_screen_source",
        index.exists(),
        {"index":str(index)},
        "Canonical one-screen GUI source is missing",
    )
    gate(
        "gui.canonical_contract",
        index.exists() and all(x in html for x in expected_endpoints[1:]),
        {"expected_endpoints":expected_endpoints},
        "Canonical GUI does not advertise every required local API lane",
    )
    gate(
        "gui.source_responsive",
        index.exists() and 'name="viewport"' in html and "@media(max-width:430px)" in html,
        None,
        "Canonical GUI phone-responsive source gates are missing",
    )
    gate(
        "gui.hero_asset",
        hero.exists() and hero.stat().st_size>0,
        {"path":str(hero),"bytes":hero.stat().st_size if hero.exists() else 0},
        "Canonical hero MP4 is missing from static/assets",
    )
    gate(
        "gui.backend_wiring_adapter",
        wiring.exists() and wiring.stat().st_size>0,
        {"path":str(wiring)},
        "GUI backend wiring adapter is missing",
    )

    device=_device_flags(home)
    for k in ("portrait","landscape","large_touch_targets","no_color_only_status","samsung_browser_or_webview"):
        gate(
            f"device.{k}",
            bool(device.get(k)),
            device.get(k),
            f"Target-phone manual verification for {k} has not been recorded",
        )

    discovery=discover(home)
    details["termux.discovery"]=discovery
    with connect(home) as con:
        runtime=[dict(r) for r in con.execute("SELECT * FROM runtime_current")]
    app_runtime=[r for r in runtime if PUBLIC_REPO.lower() in (r.get("remote") or "").lower()]
    gate(
        "termux.app_discovered",
        bool(app_runtime),
        {"matches":app_runtime},
        "The Radar source checkout has not been discovered on the target phone",
    )
    gate(
        "termux.app_live",
        any(r.get("phone_status") in {"LIVE","BYPASS_LIVE"} and r.get("health_state")=="LIVE" for r in app_runtime),
        {"matches":app_runtime},
        "The Radar target-phone runtime has not produced LIVE health evidence",
    )

    manuals=generate_all(home)
    details["manuals.generate"]=manuals
    manual_missing=[]
    for key in MANUALS:
        cur=home/"manuals"/key/"CURRENT.json"
        if not cur.exists():
            manual_missing.append(key)
            continue
        d=Path(json.loads(cur.read_text(encoding="utf-8"))["path"])
        for ext in FORMATS:
            if not list(d.glob(f"*.{ext}")):
                manual_missing.append(f"{key}.{ext}")
    gate(
        "manuals.all_formats",
        not manual_missing,
        {"missing":manual_missing},
        "One or more required manual outputs are missing",
    )

    ex=export_everything(home)
    details["export"]=ex
    export_ok=ex.get("status")=="OK" and Path(ex.get("zip","")).exists()
    gate(
        "export.zip_manifest_hashes",
        export_ok,
        {"zip":ex.get("zip"),"sha256":ex.get("sha256")},
        "EXPORT EVERYTHING did not produce a verified archive",
    )
    try:
        if not export_ok:
            raise RuntimeError("export gate did not produce a usable ZIP")
        with tempfile.TemporaryDirectory(prefix="lokivelli-acceptance-restore-") as td:
            restored=restore_export(Path(ex["zip"]),Path(td)/"clean")
            gate(
                "recovery.clean_restore",
                restored.get("status")=="OK",
                restored,
                "Clean-install export restore did not pass",
            )
    except Exception as e:
        gate(
            "recovery.clean_restore",
            False,
            {"error":str(e)},
            "Clean-install export restore raised an error",
        )

    migration=migrate_database(home)
    details["database.migration"]=migration
    gate(
        "update.database_migration",
        migration.get("status")=="OK",
        migration,
        "Database migration gate failed",
    )

    source_verify=verify_source(source_dir)
    details["source.verify"]=source_verify
    gate(
        "source.compile_and_tests",
        source_verify.get("status")=="OK",
        source_verify,
        "Source compile/test verification failed",
    )

    status="OK" if not failed else "HOLD"
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    result={
        "status":status,
        "run_id":run_id,
        "run_at":utcnow(),
        "completed":completed,
        "failed":failed,
        "blockers":blockers,
        "details":details,
    }
    with connect(home) as con:
        con.execute(
            "INSERT INTO acceptance_runs(run_id,run_at,status,completed_json,failed_json,blocker_json,result_json) VALUES(?,?,?,?,?,?,?)",
            (
                run_id,
                result["run_at"],
                status,
                json.dumps(completed,sort_keys=True),
                json.dumps(failed,sort_keys=True),
                json.dumps(blockers,sort_keys=True),
                json.dumps(result,sort_keys=True,default=str),
            ),
        )
    receipt=write_receipt(
        "acceptance.run",
        status=status,
        result={"run_id":run_id,"completed":len(completed),"failed":len(failed),"blockers":blockers},
        home=home,
    )
    result["receipt"]=receipt
    return result
