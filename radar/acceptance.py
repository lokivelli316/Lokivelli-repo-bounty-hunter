from __future__ import annotations
import json, tempfile
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, load_config
from .db import connect
from .receipts import sha256_file, write_receipt
from .github_client import pull_inventory, resolve_token
from .trending import sweep
from .termux import discover
from .manuals import MANUALS, generate_all
from .exporter import export_everything, restore_export
from .update import verify_source, migrate_database

PUBLIC_REPO="lokivelli316/Lokivelli-repo-bounty-hunter"
FORMATS=("html","pdf","md","json","csv")

def _receipt_success(home:Path, operations:set[str]):
    found=[]
    for p in (home/"evidence"/"receipts").glob("*.json"):
        try:
            d=json.loads(p.read_text(encoding="utf-8"))
            if d.get("operation") in operations and d.get("status")=="OK": found.append(d)
        except Exception: pass
    return sorted(found,key=lambda x:x.get("timestamp","") or "",reverse=True)

def _device_flags(home:Path):
    p=home/"config"/"device_acceptance.json"
    if not p.exists(): return {"portrait":False,"landscape":False,"large_touch_targets":False,"no_color_only_status":False,"samsung_browser_or_webview":False}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}

def save_device_acceptance(flags:dict,home:Path=APP_HOME):
    allowed={"portrait","landscape","large_touch_targets","no_color_only_status","samsung_browser_or_webview"}
    data={k:bool(flags.get(k)) for k in allowed}
    p=home/"config"/"device_acceptance.json"; p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(".tmp"); tmp.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8"); tmp.replace(p)
    r=write_receipt("device.acceptance.record",result=data,home=home)
    return {"status":"OK","device":data,"receipt":r}

def run_acceptance(home:Path=APP_HOME,source_dir:Path|None=None,network_refresh=True):
    source_dir=source_dir or Path(__file__).resolve().parents[1]
    cfg=load_config(home); completed=[]; failed=[]; blockers=[]; details={}
    def gate(name,passed,detail=None,blocker=None):
        (completed if passed else failed).append(name)
        details[name]=detail
        if not passed and blocker: blockers.append({"gate":name,"blocker":blocker})
        return passed

    token,_=resolve_token(home)
    gate("github.auth.present",bool(token),{"state":"PRESENT" if token else "MISSING"},"GitHub credential is not available to the local Termux application")
    if network_refresh and token:
        inv=pull_inventory(home); details["github.inventory.live_refresh"]=inv
    else:
        inv=None
    with connect(home) as con:
        owned_db=con.execute("SELECT COUNT(*) FROM repositories WHERE ownership='owned' AND github_present=1").fetchone()[0]
        stars_db=con.execute("SELECT COUNT(*) FROM stars_current").fetchone()[0]
        star_ts=con.execute("SELECT COUNT(*) FROM stars_current WHERE starred_at IS NOT NULL").fetchone()[0]
    if inv:
        gate("github.owned.pagination_and_count",inv.get("status")=="OK" and inv.get("owned_count")==owned_db,{"api":inv.get("owned_count"),"db":owned_db},"Owned repository live inventory did not verify")
        gate("github.stars.pagination_and_count",inv.get("status")=="OK" and inv.get("star_count")==stars_db,{"api":inv.get("star_count"),"db":stars_db},"Star live inventory did not verify")
    else:
        gate("github.owned.pagination_and_count",owned_db>0,{"db":owned_db},"No live inventory refresh was executed and no current owned inventory exists")
        gate("github.stars.pagination_and_count",stars_db>=0,{"db":stars_db},"No current star inventory exists")
    gate("github.star_timestamps",stars_db==0 or star_ts==stars_db,{"stars":stars_db,"with_timestamp":star_ts},"One or more current Stars lack starred_at evidence")
    writes=_receipt_success(home,{"repo.star","repo.unstar"})
    gate("github.star_write_authority",bool(writes),{"successful_write_receipts":len(writes)},"No successful STAR/UNSTAR receipt exists yet; write authority has not been behaviorally verified")

    if network_refresh and token:
        trend=sweep(home,priority_only=False); details["trending.live_sweep"]=trend
    with connect(home) as con:
        for period in ("daily","weekly","monthly"):
            src=con.execute("SELECT * FROM trending_sources WHERE period=? AND language_filter='' ORDER BY captured_at DESC LIMIT 1",(period,)).fetchone()
            ok=bool(src and src["status"]=="OK" and src["repository_count"]>0)
            gate(f"trending.all.{period}",ok,dict(src) if src else None,f"ALL {period} Trending has no successful non-empty verified snapshot")
        for lang in [x for x in cfg.get("languages",[]) if x.get("enabled")]:
            for period in ("daily","weekly","monthly"):
                src=con.execute("SELECT * FROM trending_sources WHERE period=? AND language_filter=? ORDER BY captured_at DESC LIMIT 1",(period,lang["slug"])).fetchone()
                ok=bool(src and src["status"]=="OK" and src["repository_count"]>0)
                gate(f"trending.{lang['slug']}.{period}",ok,{"status":src["status"],"count":src["repository_count"]} if src else None,f"Enabled language {lang['slug']} {period} has no successful non-empty verified snapshot")
        source_rows=[dict(r) for r in con.execute("SELECT * FROM trending_sources WHERE status='OK'")]
    hash_fail=[]
    for src in source_rows:
        p=Path(src.get("raw_path") or "")
        if not p.exists() or not src.get("raw_html_hash") or sha256_file(p)!=src["raw_html_hash"]: hash_fail.append(src.get("snapshot_id"))
    gate("trending.raw_evidence_hashes",not hash_fail,{"checked":len(source_rows),"failed":hash_fail},"One or more successful Trending snapshots lack matching raw HTML hash evidence")

    static_ok=all((source_dir/"static"/x).exists() for x in ("index.html","styles.css","app.js"))
    gate("gui.one_screen_source",static_ok,{"static":str(source_dir/"static")},"One-screen GUI source files are missing")
    css=(source_dir/"static"/"styles.css").read_text(encoding="utf-8") if (source_dir/"static"/"styles.css").exists() else ""
    gate("gui.source_responsive",("@media(max-width:700px)" in css and "prefers-reduced-motion" in css),None,"Responsive/reduced-motion source gates are missing")
    device=_device_flags(home)
    for k in ("portrait","landscape","large_touch_targets","no_color_only_status","samsung_browser_or_webview"):
        gate(f"device.{k}",bool(device.get(k)),device.get(k),f"Target-phone manual verification for {k} has not been recorded")

    discovery=discover(home); details["termux.discovery"]=discovery
    with connect(home) as con:
        runtime=[dict(r) for r in con.execute("SELECT * FROM runtime_current")]
    app_runtime=[r for r in runtime if PUBLIC_REPO.lower() in (r.get("remote") or "").lower()]
    gate("termux.app_discovered",bool(app_runtime),{"matches":app_runtime},"The Radar source checkout has not been discovered on the target phone")
    gate("termux.app_live",any(r.get("phone_status") in {"LIVE","BYPASS_LIVE"} and r.get("health_state")=="LIVE" for r in app_runtime),{"matches":app_runtime},"The Radar target-phone runtime has not produced LIVE health evidence")

    manuals=generate_all(home); details["manuals.generate"]=manuals
    manual_missing=[]
    for key in MANUALS:
        cur=home/"manuals"/key/"CURRENT.json"
        if not cur.exists(): manual_missing.append(key); continue
        d=Path(json.loads(cur.read_text())["path"])
        for ext in FORMATS:
            if not list(d.glob(f"*.{ext}")): manual_missing.append(f"{key}.{ext}")
    gate("manuals.all_formats",not manual_missing,{"missing":manual_missing},"One or more required manual outputs are missing")

    ex=export_everything(home); details["export"]=ex
    gate("export.zip_manifest_hashes",ex.get("status")=="OK" and Path(ex.get("zip","")).exists(),{"zip":ex.get("zip"),"sha256":ex.get("sha256")},"EXPORT EVERYTHING did not produce a verified archive")
    try:
        with tempfile.TemporaryDirectory(prefix="lokivelli-acceptance-restore-") as td:
            restored=restore_export(Path(ex["zip"]),Path(td)/"clean")
            gate("recovery.clean_restore",restored.get("status")=="OK",restored,"Clean-install export restore did not pass")
    except Exception as e:
        gate("recovery.clean_restore",False,{"error":str(e)},"Clean-install export restore raised an error")

    migration=migrate_database(home); details["database.migration"]=migration
    gate("update.database_migration",migration.get("status")=="OK",migration,"Database migration gate failed")
    source_verify=verify_source(source_diŠNÈ]Z[ÖÈœÛİ\˜ÙK™\šYH—O\Ûİ\˜ÙWİ™\šYBˆØ]J\]KœÛİ\˜ÙWİ™\šYH‹Ûİ\˜ÙWİ™\šYK™Ù]
œİ]\ÈŠOOH“ÒÈ‹Ûİ\˜ÙWİ™\šYK”Ûİ\˜ÙH™\šYšXØ][Ûˆ˜Z[YŠBˆ›Û˜XÚ×Ü™XÙZ\ÏWÜ™XÙZ\ÜİXØÙ\ÜÊÛYKÈ˜\œ›Û˜XÚÈŸJBˆØ]Jœ™XÛİ™\Kœ›Û˜XÚ×Ø™Z]š[Üˆ‹›ÛÛ
›Û˜XÚ×Ü™XÙZ\ÊKÈœİXØÙ\ÜÙ[Ü›Û˜XÚ×Ü™XÙZ\È›[Š›Û˜XÚ×Ü™XÙZ\Ê_K“›ÈİXØÙ\ÜÙ[›Û˜XÚÈ^Xİ][Ûˆ™XÙZ\^\İÈÛˆH\™Ù][œİ[][ÛˆŠB‚ˆİ]\ÏH“ÒÈˆYˆ›İ˜Z[Y[ÙH’Ó‚ˆ[—ÚYY]][YK››İÊ[Y^›Û™K]ÊKœİ™[YJ‰VI[IY	R	SITË‰Y–ˆŠBˆ™\İ[^Èœİ]\Èœİ]\Ëœ[—ÚYœ[—ÚY˜ÛÛ\]YÙØ]\È˜ÛÛ\]Y™˜Z[YÙØ]\È™˜Z[Y˜›ØÚÙ\œÈ˜›ØÚÙ\œË™]Z[È™]Z[Ëˆ›™^Ù^Xİ]X›WØXİ[Ûˆ˜›ØÚÙ\œÖÌHYˆ›ØÚÙ\œÈ[ÙHÈ™Ø]Hˆ˜ÛÛ\][Ûˆ‹˜›ØÚÙ\ˆ“›Û™__BˆÚ]ÛÛ›™Xİ
ÛYJH\ÈÛÛ‚ˆÛÛ‹™^Xİ]J’S”ÑT•S•ÈXØÙ\[˜ÙWÜ[œÊ[—ÚY[—Ø]İ]\ËÛÛ\]YÚœÛÛ‹˜Z[YÚœÛÛ‹›ØÚÙ\—ÚœÛÛ‹™\İ[ÚœÛÛŠHSQTÊËËËËËËÊH‹ˆ
[—ÚY]][YK››İÊ[Y^›Û™K]ÊKš\ÛÙ›Ü›X]

Kİ]\ËœÛÛ‹™[\ÊÛÛ\]Y
KœÛÛ‹™[\Ê˜Z[Y
KœÛÛ‹™[\Ê›ØÚÙ\œÊKœÛÛ‹™[\Ê™\İ[Y˜][\İŠJJBˆ™XÙZ\]Üš]WÜ™XÙZ\
˜XØÙ\[˜ÙKœ[ˆ‹[œ]Ï^È›™]ÛÜš×Ü™Yœ™\Ú›™]ÛÜš×Ü™Yœ™\ÚK™\İ[^Èœ[—ÚYœ[—ÚY˜ÛÛ\]Y›[ŠÛÛ\]Y
K™˜Z[Y›[Š˜Z[Y
K˜›ØÚÙ\œÈ˜›ØÚÙ\œßKİ]\Ï\İ]\ËÛYOZÛYJBˆ™\İ[Èœ™XÙZ\—O\™XÙZ\ˆ™]\›ˆ™\İ[