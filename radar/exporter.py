from __future__ import annotations
import csv, json, os, shutil, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, ensure_layout, load_config
from .db import connect
from .manuals import MANUALS, generate_all
from .receipts import sha256_file, write_receipt, utcnow

FILE_NAMES={
 "owned-termux":"owned_repo_termux",
 "favorites":"favorites",
 "forks":"forks",
 "trending":"trending_radar",
 "runtime":"runtime_register",
 "failure-atlas":"failure_workaround_bypass_atlas",
}

def _current_manual_dir(home,key):
    p=home/"manuals"/key/"CURRENT.json"
    if not p.exists(): return None
    return Path(json.loads(p.read_text())["path"])

def _json_dump(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True),encoding="utf-8")

def _csv_dump(path,rows):
    fields=sorted({k for r in rows for k in r}) if rows else []
    with path.open("w",newline="",encoding="utf-8") as f:
        if fields:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            w.writerows([{k:r.get(k) for k in fields} for r in rows])

def _redact_config(cfg):
    secret_words=("token","secret","password","credential","key")
    def walk(x,k=""):
        if isinstance(x,dict):
            return {kk:("REDACTED" if any(s in kk.lower() for s in secret_words) else walk(vv,kk)) for kk,vv in x.items()}
        if isinstance(x,list): return [walk(v,k) for v in x]
        return x
    return walk(cfg)

def export_everything(home:Path=APP_HOME):
    ensure_layout(home)
    if any(_current_manual_dir(home,k) is None for k in MANUALS): generate_all(home)
    stamp=datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    zip_name=f"LOKIVELLI_RADAR_MANUAL_EXPORT_{stamp}.zip"
    out=home/"exports"/zip_name
    with tempfile.TemporaryDirectory(prefix="lokivelli-export-") as td:
        root=Path(td)
        for name in ("manuals","data","tables","evidence","config"): (root/name).mkdir()
        for key in MANUALS:
            d=_current_manual_dir(home,key); base=FILE_NAMES[key]
            for ext in ("pdf","html","md","json","csv"):
                src=next(d.glob(f"*.{ext}"),None)
                if src: shutil.copy2(src,root/"manuals"/f"{base}.{ext}")
        with connect(home) as con:
            owned=[dict(r) for r in con.execute("SELECT * FROM repositories WHERE ownership='owned' AND fork=0 ORDER BY full_name")]
            fav=[dict(r) for r in con.execute("SELECT r.*,s.star_position_current,s.starred_at,s.last_seen_in_stars FROM stars_current s JOIN repositories r ON r.repo_id=s.repo_id ORDER BY s.star_position_current")]
            forks=[dict(r) for r in con.execute("SELECT * FROM repositories WHERE fork=1 ORDER BY full_name")]
            trending=[dict(r) for r in con.execute("SELECT * FROM trending_snapshots ORDER BY captured_at,period,language_filter,position")]
            runtime=[dict(r) for r in con.execute("SELECT * FROM runtime_current ORDER BY path")]
            events=[dict(r) for r in con.execute("SELECT * FROM events ORDER BY event_id")]
            sources=[dict(r) for r in con.execute("SELECT * FROM trending_sources ORDER BY captured_at")]
            versions=[dict(r) for r in con.execute("SELECT * FROM manual_versions ORDER BY generated_at")]
        datasets={"owned_repositories":owned,"favorites":fav,"forks":forks,"trending":trending,"runtime":runtime,"events":events,"trending_sources":sources,"manual_versions":versions}
        for name,rows in datasets.items(): _json_dump(root/"data"/f"{name}.json",rows)
        for name in ("owned_repositories","favorites","forks","trending","runtime"): _csv_dump(root/"tables"/f"{name}.csv",datasets[name])
        receipts=[]
        for p in sorted((home/"evidence"/"receipts").glob("*.json")):
            try: receipts.append(json.loads(p.read_text()))
            except Exception: pass
        with (root/"data"/"receipts.jsonl").open("w",encoding="utf-8") as f:
            for r in receipts: f.write(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n")
        _json_dump(root/"evidence"/"source_metadata.json",{"trending_sources":sources,"exported_at":utcnow()})
        _json_dump(root/"config"/"config.redacted.json",_redact_config(load_config(home)))
        (root/"README.txt").write_text(
            "LOKIVELLI TERMUX GITHUB RADAR + AUTO-MANUAL FORGE EXPORT\n\n"
            "This archive contains generated manuals plus machine-readable operational state.\n"
            "Secret values are default-denied and are not included. Verify SHA256SUMS before restore.\n"
            "Restore with: lokivelli-radar restore <this-zip> --home <clean-home>\n",encoding="utf-8")
        files=[p for p in root.rglob("*") if p.is_file()]
        hashes={str(p.relative_to(root)):sha256_file(p) for p in files}
        manifest={"format":"LOKIVELLI_RADAR_EXPORT_V1","created_at":utcnow(),"files":hashes,"datasets":{k:len(v) for k,v in datasets.items()},"secret_policy":"DEFAULT_DENY"}
        _json_dump(root/"MANIFEST.json",manifest)
        hashes["MANIFEST.json"]=sha256_file(root/"MANIFEST.json")
        (root/"SHA256SUMS").write_text("".join(f"{h}  {name}\n" for name,h in sorted(hashes.items())),encoding="utf-8")
        with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for p in root.rglob("*"):
                if p.is_file(): z.write(p,p.relative_to(root))
    receipt=write_receipt("manual.export",result={"zip":str(out),"sha256":sha256_file(out)},output_hashes={zip_name:sha256_file(out)},home=home)
    return {"status":"OK","zip":str(out),"sha256":sha256_file(out),"receipt":receipt}

def _verify_extract(zip_path:Path,dest:Path):
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target=(dest/info.filename).resolve()
            if not str(target).startswith(str(dest.resolve())+os.sep): raise RuntimeError("unsafe zip path")
        z.extractall(dest)
    sums={}
    for line in (dest/"SHA256SUMS").read_text().splitlines():
        if not line.strip(): continue
        h,name=line.split("  ",1); sums[name]=h
    for name,h in sums.items():
        p=dest/name
        if not p.exists() or sha256_file(p)!=h: raise RuntimeError(f"hash mismatch: {name}")

def restore_export(zip_path:Path, home:Path):
    ensure_layout(home)
    with tempfile.TemporaryDirectory(prefix="lokivelli-restore-") as td:
        root=Path(td); _verify_extract(zip_path,root)
        data={n:json.loads((root/"data"/f"{n}.json").read_text()) for n in ("owned_repositories","favorites","forks","trending","runtime","events","trending_sources","manual_versions")}
        with connect(home) as con:
            con.execute("DELETE FROM stars_current"); con.execute("DELETE FROM trending_snapshots"); con.execute("DELETE FROM trending_sources"); con.execute("DELETE FROM runtime_current"); con.execute("DELETE FROM events")
            repos={}
            for group in (data["owned_repositories"],data["favorites"],data["forks"]):
                for r in group: repos[r["repo_id"]]=r
            repo_cols=[r[1] for r in con.execute("PRAGMA table_info(repositories)")]
            for r in repos.values():
                vals={k:r.get(k) for k in repo_cols}
                con.execute(f"INSERT OR REPLACE INTO repositories({','.join(repo_cols)}) VALUES({','.join('?' for _ in repo_cols)})",tuple(vals[k] for k in repo_cols))
            for r in data["favorites"]:
                con.execute("INSERT INTO stars_current(repo_id,star_position_current,starred_at,last_seen_in_stars) VALUES(?,?,?,?)",(r["repo_id"],r["star_position_current"],r.get("starred_at"),r.get("last_seen_in_stars") or utcnow()))
            for name,table in (("trending","trending_snapshots"),("runtime","runtime_current"),("events","events"),("trending_sources","trending_sources")):
                cols=[r[1] for r in con.execute(f"PRAGMA table_info({table})")]
                for row in data[name]:
                    usable=[c for c in cols if c in row and not (table=="events" and c=="event_id")]
                    con.execute(f"INSERT OR REPLACE INTO {table}({','.join(usable)}) VALUES({','.join('?' for _ in usable)})",tuple(row.get(c) for c in usable))
        pred=home/"manuals"/"imported-predecessor"/datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
        pred.mkdir(parents=True,exist_ok=True)
        shutil.copytree(root/"manuals",pred/"manuals",dirs_exist_ok=True)
    receipt=write_receipt("backup.restore",inputs={"zip":str(zip_path)},result={"home":str(home)},home=home)
    return {"status":"OK","home":str(home),"receipt":receipt}
