from __future__ import annotations
import csv, html, json, os
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, ensure_layout
from .db import connect
from .pdfmini import write_text_pdf
from .receipts import sha256_file, utcnow, write_receipt

MANUALS={
 "owned-termux":"01_LOKIVELLIAN_REPO_AND_TERMUX_MANUAL",
 "favorites":"02_LOKIVELLIS_FIELD_FAVORITES",
 "forks":"03_LOKIVELLIAN_FORKED_REPOSITORY_MANUAL",
 "trending":"04_GITHUB_TRENDING_RADAR",
 "runtime":"05_CURRENT_PHONE_RUNTIME_REGISTER",
 "failure-atlas":"06_FAILURE_WORKAROUND_BYPASS_ATLAS",
}

def _jsonish(value, default):
    if value is None: return default
    if isinstance(value,(dict,list)): return value
    try: return json.loads(value)
    except Exception: return default

def _receipt_refs(full_name:str,home:Path):
    refs=[]
    for p in sorted((home/"evidence"/"receipts").glob("*.json"),reverse=True):
        try:
            data=json.loads(p.read_text(encoding="utf-8"))
            if full_name in json.dumps(data,ensure_ascii=False): refs.append(data.get("receipt_id"))
        except Exception: pass
        if len(refs)>=50: break
    return [x for x in refs if x]

def repository_card_from_row(con,row:dict,home:Path):
    full=row.get("full_name")
    events=[dict(r) for r in con.execute("SELECT event_type,at,previous_json,current_json,evidence_ref FROM events WHERE object_key=? ORDER BY at",(full,))]
    failures=[e for e in events if "FAIL" in e["event_type"] or "HOLD" in e["event_type"]]
    workarounds=[e for e in events if "WORKAROUND" in e["event_type"]]
    bypasses=[e for e in events if "BYPASS" in e["event_type"]]
    notes=[dict(r) for r in con.execute("SELECT namespace,note,updated_at FROM notes WHERE object_key=? ORDER BY updated_at",(full,))]
    readmes=[dict(r) for r in con.execute("SELECT fetched_at,source_url,source_hash,status FROM readme_audits WHERE full_name=? ORDER BY fetched_at DESC LIMIT 20",(full,))]
    trendrefs=[r[0] for r in con.execute("SELECT DISTINCT source_hash FROM trending_snapshots WHERE full_name=? ORDER BY captured_at DESC LIMIT 20",(full,))]
    card=dict(row)
    card["topics"]=_jsonish(card.pop("topics_json",None),[])
    card["dependencies"]=_jsonish(card.pop("dependencies_json",None),[])
    card["platform_requirements"]=_jsonish(card.pop("platform_requirements_json",None),[])
    card["known_failures"]=failures
    card["workarounds"]=workarounds
    card["bypasses"]=bypasses
    card["manual_notes"]=notes
    card["evidence_refs"]=[x["source_hash"] for x in readmes]+trendrefs
    card["receipt_refs"]=_receipt_refs(full,home)
    return card

def get_repository_card(full_name:str,home:Path=APP_HOME):
    with connect(home) as con:
        row=con.execute("SELECT * FROM repositories WHERE full_name=?",(full_name,)).fetchone()
        if not row: return {"status":"HOLD","error":"repository record not found","full_name":full_name}
        card=repository_card_from_row(con,dict(row),home)
        fav=con.execute("SELECT * FROM favorite_state WHERE repo_id=?",(row["repo_id"],)).fetchone()
        fork=con.execute("SELECT * FROM fork_state WHERE repo_id=?",(row["repo_id"],)).fetchone()
        if fav:
            fd=dict(fav); fd["related_owned_repos"]=_jsonish(fd.pop("related_owned_repos_json",None),[]); fd["related_favorites"]=_jsonish(fd.pop("related_favorites_json",None),[]); card["favorite_state"]=fd
        if fork: card["fork_state"]=dict(fork)
        return {"status":"OK","card":card}

def _rows(con,key,home):
    if key=="owned-termux":
        return [repository_card_from_row(con,dict(r),home) for r in con.execute("SELECT * FROM repositories WHERE ownership='owned' AND fork=0 ORDER BY github_present DESC,full_name")]
    if key=="favorites":
        rows=[]
        for r in con.execute("""SELECT r.*,s.star_position_current,s.starred_at,s.last_seen_in_stars,
            f.first_seen_in_manual,f.readme_audit_state,f.documented_checkout,f.documented_setup,f.platform_notes,
            f.operator_classification,f.operator_notes,f.tested_on_phone,f.installed_on_phone,f.adopted_into_stack,
            f.related_owned_repos_json,f.related_favorites_json
            FROM stars_current s JOIN repositories r ON r.repo_id=s.repo_id
            LEFT JOIN favorite_state f ON f.repo_id=r.repo_id ORDER BY s.star_position_current"""):
            d=repository_card_from_row(con,dict(r),home)
            d["related_owned_repos"]=_jsonish(d.pop("related_owned_repos_json",None),[])
            d["related_favorites"]=_jsonish(d.pop("related_favorites_json",None),[])
            rows.append(d)
        return rows
    if key=="forks":
        return [repository_card_from_row(con,dict(r),home) for r in con.execute("SELECT r.*,f.upstream_status,f.local_modifications,f.adoption_state FROM repositories r LEFT JOIN fork_state f ON f.repo_id=r.repo_id WHERE r.ownership='owned' AND r.fork=1 ORDER BY r.github_present DESC,r.full_name")]
    if key=="trending": return [dict(r) for r in con.execute("SELECT t.* FROM trending_snapshots t JOIN (SELECT period,language_filter,MAX(captured_at) c FROM trending_snapshots GROUP BY period,language_filter) x ON t.period=x.period AND t.language_filter=x.language_filter AND t.captured_at=x.c ORDER BY t.period,t.language_filter,t.position")]
    if key=="runtime": return [dict(r) for r in con.execute("SELECT * FROM runtime_current ORDER BY path")]
    if key=="failure-atlas": return [dict(r) for r in con.execute("SELECT * FROM events WHERE event_type LIKE '%FAIL%' OR event_type LIKE '%HOLD%' OR event_type LIKE '%WORKAROUND%' OR event_type LIKE '%BYPASS%' OR event_type LIKE '%MISSING%' ORDER BY at DESC")]
    return []

def _md(title,generated,rows):
    out=[f"# {title}","",f"Generated: {generated}","","> Evidence-backed generated snapshot. Historical predecessors are preserved separately.",""]
    if not rows: out += ["No current records.",""]
    for i,row in enumerate(rows,1):
        label=row.get("full_name") or row.get("path") or row.get("object_key") or f"Record {i}"
        out += [f"## {i}. {label}",""]
        for k,v in row.items():
            out.append(f"- **{k}**: {json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}")
        out.append("")
    return "\n".join(out)

def _html(title,generated,rows):
    cards=[]
    for row in rows:
        label=row.get("full_name") or row.get("path") or row.get("object_key") or "Record"
        fields="".join(f"<dt>{html.escape(str(k))}</dt><dd>{html.escape(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v))}</dd>" for k,v in row.items())
        cards.append(f"<article><h2>{html.escape(str(label))}</h2><dl>{fields}</dl></article>")
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>body{{font-family:system-ui;background:#080b10;color:#f7f7f7;max-width:1100px;margin:auto;padding:24px}}article{{border:2px solid #7f8ea3;border-radius:14px;padding:16px;margin:12px 0}}dt{{font-weight:800;color:#d7e5ff}}dd{{margin:0 0 8px 0;overflow-wrap:anywhere}}.meta{{font-size:1.1rem}}</style></head><body><h1>{html.escape(title)}</h1><p class="meta">Generated {html.escape(generated)}</p>{''.join(cards) if cards else '<p>No current records.</p>'}</body></html>'''

def generate_all(home:Path=APP_HOME):
    ensure_layout(home); generated=utcnow(); version=datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S.%fZ"); result={}
    with connect(home) as con:
        for key,title in MANUALS.items():
            rows=_rows(con,key,home); d=home/"manuals"/key/version; d.mkdir(parents=True,exist_ok=True)
            md=d/f"{title}.md"; htm=d/f"{title}.html"; js=d/f"{title}.json"; csvp=d/f"{title}.csv"; pdf=d/f"{title}.pdf"
            md.write_text(_md(title,generated,rows),encoding="utf-8")
            htm.write_text(_html(title,generated,rows),encoding="utf-8")
            js.write_text(json.dumps({"manual":title,"generated_at":generated,"records":rows},indent=2,ensure_ascii=False,sort_keys=True),encoding="utf-8")
            flatrows=[]
            for row in rows:
                flatrows.append({k:(json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v) for k,v in row.items()})
            if flatrows:
                fields=sorted({k for r in flatrows for k in r})
                with csvp.open("w",newline="",encoding="utf-8") as f:
                    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows([{k:r.get(k) for k in fields} for r in flatrows])
            else: csvp.write_text("",encoding="utf-8")
            lines=md.read_text(encoding="utf-8").splitlines(); write_text_pdf(pdf,title,lines)
            hashes={p.name:sha256_file(p) for p in (md,htm,js,csvp,pdf)}
            content_hash=hashes[js.name]
            predecessor=con.execute("SELECT version_id FROM manual_versions WHERE manual_key=? ORDER BY generated_at DESC LIMIT 1",(key,)).fetchone()
            con.execute("INSERT INTO manual_versions(manual_key,version_id,generated_at,content_hash,path,predecessor_ref,evidence_json) VALUES(?,?,?,?,?,?,?)",
                        (key,version,generated,content_hash,str(d),predecessor[0] if predecessor else None,json.dumps(hashes,sort_keys=True)))
            current=home/"manuals"/key/"CURRENT.json"; tmp=current.with_suffix(".tmp")
            tmp.write_text(json.dumps({"manual":title,"version_id":version,"generated_at":generated,"path":str(d),"hashes":hashes},indent=2,sort_keys=True),encoding="utf-8"); os.replace(tmp,current)
            result[key]={"title":title,"version":version,"path":str(d),"records":len(rows),"hashes":hashes}
    receipt=write_receipt("manual.generate",result=result,source="SQLite operational evidence",home=home)
    return {"status":"OK","manuals":result,"receipt":receipt}
