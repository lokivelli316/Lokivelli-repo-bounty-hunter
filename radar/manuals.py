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

def _rows(con,key):
    if key=="owned-termux": return [dict(r) for r in con.execute("SELECT * FROM repositories WHERE ownership='owned' AND fork=0 ORDER BY full_name")]
    if key=="favorites": return [dict(r) for r in con.execute("SELECT r.*,s.star_position_current,s.starred_at,s.last_seen_in_stars FROM stars_current s JOIN repositories r ON r.repo_id=s.repo_id ORDER BY s.star_position_current")]
    if key=="forks": return [dict(r) for r in con.execute("SELECT * FROM repositories WHERE fork=1 ORDER BY full_name")]
    if key=="trending": return [dict(r) for r in con.execute("SELECT t.* FROM trending_snapshots t JOIN (SELECT period,language_filter,MAX(captured_at) c FROM trending_snapshots GROUP BY period,language_filter) x ON t.period=x.period AND t.language_filter=x.language_filter AND t.captured_at=x.c ORDER BY t.period,t.language_filter,t.position")]
    if key=="runtime": return [dict(r) for r in con.execute("SELECT * FROM runtime_current ORDER BY path")]
    if key=="failure-atlas": return [dict(r) for r in con.execute("SELECT * FROM events WHERE event_type LIKE '%FAIL%' OR event_type LIKE '%HOLD%' OR event_type LIKE '%WORKAROUND%' OR event_type LIKE '%BYPASS%' ORDER BY at DESC")]
    return []

def _md(title,generated,rows):
    out=[f"# {title}","",f"Generated: {generated}","","> Evidence-backed generated snapshot. Historical predecessors are preserved separately.",""]
    if not rows: out += ["No current records.",""]
    for i,row in enumerate(rows,1):
        label=row.get("full_name") or row.get("path") or row.get("object_key") or f"Record {i}"
        out += [f"## {i}. {label}",""]
        for k,v in row.items():
            if k in {"topics_json","dependencies_json","platform_requirements_json","previous_json","current_json"} and isinstance(v,str):
                try: v=json.loads(v)
                except Exception: pass
            out.append(f"- **{k}**: {json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v}")
        out.append("")
    return "\n".join(out)

def _html(title,generated,rows):
    cards=[]
    for row in rows:
        label=row.get("full_name") or row.get("path") or row.get("object_key") or "Record"
        fields="".join(f"<dt>{html.escape(str(k))}</dt><dd>{html.escape(str(v))}</dd>" for k,v in row.items())
        cards.append(f"<article><h2>{html.escape(str(label))}</h2><dl>{fields}</dl></article>")
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>body{{font-family:system-ui;background:#080b10;color:#f7f7f7;max-width:1100px;margin:auto;padding:24px}}article{{border:2px solid #7f8ea3;border-radius:14px;padding:16px;margin:12px 0}}dt{{font-weight:800;color:#d7e5ff}}dd{{margin:0 0 8px 0;overflow-wrap:anywhere}}.meta{{font-size:1.1rem}}</style></head><body><h1>{html.escape(title)}</h1><p class="meta">Generated {html.escape(generated)}</p>{''.join(cards) if cards else '<p>No current records.</p>'}</body></html>'''

def generate_all(home:Path=APP_HOME):
    ensure_layout(home); generated=utcnow(); version=datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ"); result={}
    with connect(home) as con:
        for key,title in MANUALS.items():
            rows=_rows(con,key); d=home/"manuals"/key/version; d.mkdir(parents=True,exist_ok=True)
            md=d/f"{title}.md"; htm=d/f"{title}.html"; js=d/f"{title}.json"; csvp=d/f"{title}.csv"; pdf=d/f"{title}.pdf"
            md.write_text(_md(title,generated,rows),encoding="utf-8")
            htm.write_text(_html(title,generated,rows),encoding="utf-8")
            js.write_text(json.dumps({"manual":title,"generated_at":generated,"records":rows},indent=2,ensure_ascii=False,sort_keys=True),encoding="utf-8")
            if rows:
                fields=sorted({k for r in rows for k in r})
                with csvp.open("w",newline="",encoding="utf-8") as f:
                    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
                    for r in rows: w.writerow({k:r.get(k) for k in fields})
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
