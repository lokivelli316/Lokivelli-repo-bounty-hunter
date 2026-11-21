from __future__ import annotations
import json
from pathlib import Path
from .config import APP_HOME, load_config
from .db import connect
from .github_client import resolve_token
from .manuals import MANUALS
from .receipts import utcnow

def _latest_trending(con,period="daily",language=""):
    src=con.execute("SELECT * FROM trending_sources WHERE period=? AND language_filter=? ORDER BY captured_at DESC LIMIT 1",(period,language)).fetchone()
    if not src: return {"source":None,"items":[]}
    rows=[]
    for r in con.execute("""SELECT t.*, CASE WHEN s.repo_id IS NULL THEN 0 ELSE 1 END already_starred,
        CASE WHEN o.repo_id IS NULL THEN 0 ELSE 1 END already_owned
        FROM trending_snapshots t
        LEFT JOIN stars_current s ON s.repo_id=t.repo_id
        LEFT JOIN repositories o ON o.repo_id=t.repo_id AND o.ownership='owned'
        WHERE t.snapshot_id=? ORDER BY t.position""",(src["snapshot_id"],)):
        d=dict(r)
        if not d["repo_id"]:
            rr=con.execute("SELECT repo_id,ownership FROM repositories WHERE full_name=?",(d["full_name"],)).fetchone()
            if rr:
                d["repo_id"]=rr["repo_id"]; d["already_starred"]=int(bool(con.execute("SELECT 1 FROM stars_current WHERE repo_id=?",(rr["repo_id"],)).fetchone())); d["already_owned"]=int(rr["ownership"]=="owned")
        stats=con.execute("SELECT MIN(captured_at) first_seen,MAX(captured_at) last_seen,COUNT(*) appearances,MIN(position) best_rank FROM trending_snapshots WHERE full_name=?",(d["full_name"],)).fetchone()
        d.update(dict(stats)); rows.append(d)
    return {"source":dict(src),"items":rows}

def dashboard(home:Path=APP_HOME,period="daily",language=""):
    cfg=load_config(home); token,_=resolve_token(home)
    with connect(home) as con:
        owned=con.execute("SELECT COUNT(*) FROM repositories WHERE ownership='owned' AND fork=0").fetchone()[0]
        forks=con.execute("SELECT COUNT(*) FROM repositories WHERE fork=1").fetchone()[0]
        stars=con.execute("SELECT COUNT(*) FROM stars_current").fetchone()[0]
        deltas=[dict(r) for r in con.execute("SELECT * FROM events ORDER BY event_id DESC LIMIT 40")]
        runtime=[dict(r) for r in con.execute("SELECT * FROM runtime_current ORDER BY phone_status DESC,path LIMIT 100")]
        trend=_latest_trending(con,period,language)
    manuals={}
    for key,title in MANUALS.items():
        p=home/"manuals"/key/"CURRENT.json"
        manuals[key]=json.loads(p.read_text()) if p.exists() else {"manual":title,"status":"NOT_GENERATED"}
    live=sum(1 for r in runtime if r.get("phone_status") in {"LIVE","BYPASS_LIVE"})
    hold=sum(1 for r in runtime if r.get("phone_status") in {"HOLD","DEGRADED"} or r.get("health_state")=="HOLD")
    return {"now":utcnow(),"auth":{"github":"PRESENT" if token else "MISSING"},"counts":{"stars":stars,"owned":owned,"forks":forks,"runtime":len(runtime),"live":live,"hold":hold},
            "trending":trend,"deltas":deltas,"runtime":runtime,"manuals":manuals,"languages":cfg.get("languages",[]),"period":period,"language":language}

def search(q:str,home:Path=APP_HOME,limit=100):
    q=q.strip(); pat=f"%{q}%"; out=[]
    if not q: return out
    with connect(home) as con:
        for r in con.execute("SELECT full_name,description,primary_language,classification,ownership,source_status,phone_status FROM repositories WHERE full_name LIKE ? OR description LIKE ? OR primary_language LIKE ? OR topics_json LIKE ? ORDER BY full_name LIMIT ?",(pat,pat,pat,pat,limit)):
            out.append({"kind":"repository",**dict(r)})
        for r in con.execute("SELECT full_name,period,language_filter,position,captured_at FROM trending_snapshots WHERE full_name LIKE ? OR description LIKE ? OR primary_language LIKE ? ORDER BY captured_at DESC LIMIT ?",(pat,pat,pat,limit)):
            out.append({"kind":"trending",**dict(r)})
        for r in con.execute("SELECT path,runtime_language,phone_status,health_state,remote FROM runtime_current WHERE path LIKE ? OR runtime_language LIKE ? OR remote LIKE ? LIMIT ?",(pat,pat,pat,limit)):
            out.append({"kind":"runtime",**dict(r)})
        for r in con.execute("SELECT event_type,object_key,at FROM events WHERE event_type LIKE ? OR object_key LIKE ? ORDER BY event_id DESC LIMIT ?",(pat,pat,limit)):
            out.append({"kind":"event",**dict(r)})
        for r in con.execute("SELECT full_name,fetched_at,source_hash,findings_json,commands_json FROM readme_audits WHERE full_name LIKE ? OR content LIKE ? OR findings_json LIKE ? OR commands_json LIKE ? ORDER BY fetched_at DESC LIMIT ?",(pat,pat,pat,pat,limit)):
            out.append({"kind":"readme",**dict(r)})
        for r in con.execute("SELECT namespace,object_key,note,updated_at FROM notes WHERE object_key LIKE ? OR note LIKE ? LIMIT ?",(pat,pat,limit)):
            out.append({"kind":"note",**dict(r)})
    return out[:limit]
