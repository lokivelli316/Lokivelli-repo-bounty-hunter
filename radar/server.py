from __future__ import annotations
import json, mimetypes, os, traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from .config import APP_HOME, load_config, save_config, ensure_layout
from .dashboard import dashboard, search
from .github_client import pull_inventory, set_star, audit_readme
from .trending import acquire, sweep
from .termux import discover, register_runtime, transition_runtime
from .manuals import generate_all, get_repository_card
from .exporter import export_everything
from .scheduler import run_once
from .receipts import utcnow, write_receipt
from .failure import record_workaround
from .history import import_predecessor
from .update import backup_state, check_update, migrate_database, verify_source, upgrade, rollback
from .acceptance import run_acceptance, save_device_acceptance
from .db import connect

STATIC=Path(__file__).resolve().parents[1]/"static"

def _json_bytes(obj): return json.dumps(obj,ensure_ascii=False,default=str).encode()

def repository_history(full_name:str,home:Path):
    with connect(home) as con:
        rows=[dict(r) for r in con.execute("SELECT period,language_filter,position,total_stars,forks,period_gain,captured_at,source_hash FROM trending_snapshots WHERE full_name=? ORDER BY captured_at DESC",(full_name,))]
        counts={p:sum(1 for r in rows if r['period']==p) for p in ('daily','weekly','monthly')}
        languages=sorted({r['language_filter'] for r in rows if r['language_filter']})
        best=min((r['position'] for r in rows),default=None)
        rr=con.execute("SELECT repo_id FROM repositories WHERE full_name=?",(full_name,)).fetchone()
        star=None
        if rr:
            sr=con.execute("SELECT starred_at FROM stars_current WHERE repo_id=?",(rr[0],)).fetchone(); star=sr[0] if sr else None
        events=[dict(r) for r in con.execute("SELECT event_type,at,previous_json,current_json,evidence_ref FROM events WHERE object_key=? ORDER BY at DESC",(full_name,))]
    return {"status":"OK","full_name":full_name,"first_seen":rows[-1]['captured_at'] if rows else None,"last_seen":rows[0]['captured_at'] if rows else None,"daily_appearances":counts['daily'],"weekly_appearances":counts['weekly'],"monthly_appearances":counts['monthly'],"best_rank":best,"languages_seen_under":languages,"operator_star_date":star,"star_gain_history":[{"captured_at":r['captured_at'],"period":r['period'],"language":r['language_filter'],"gain":r['period_gain']} for r in rows],"appearances":rows,"events":events}

def repository_compare(full_name:str,home:Path):
    card=get_repository_card(full_name,home)
    with connect(home) as con:
        latest=[dict(r) for r in con.execute("SELECT period,language_filter,position,total_stars,forks,period_gain,captured_at FROM trending_snapshots WHERE full_name=? ORDER BY captured_at DESC LIMIT 20",(full_name,))]
        runtime=[dict(r) for r in con.execute("SELECT * FROM runtime_current WHERE remote LIKE ? ORDER BY probed_at DESC",(f"%{full_name}%",))]
    return {"status":card.get("status","HOLD"),"full_name":full_name,"manual_card":card.get("card"),"trending":latest,"runtime":runtime}

class Handler(BaseHTTPRequestHandler):
    server_version="LokivelliRadar/0.2"
    def log_message(self,fmt,*args):
        ensure_layout(self.server.home)
        with (self.server.home/"logs"/"server.log").open("a",encoding="utf-8") as f: f.write(f"{utcnow()} {self.address_string()} {fmt%args}\n")
    def send_json(self,obj,status=200):
        data=_json_bytes(obj); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def body(self):
        n=int(self.headers.get("Content-Length","0") or 0); raw=self.rfile.read(n) if n else b"{}"; return json.loads(raw or b"{}")
    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query); home=self.server.home
        try:
            if u.path=="/api/dashboard": return self.send_json(dashboard(home,q.get("period",["daily"])[0],q.get("language",[""])[0]))
            if u.path=="/api/search": return self.send_json({"results":search(q.get("q",[""])[0],home)})
            if u.path=="/api/config": return self.send_json(load_config(home))
            if u.path=="/api/history": return self.send_json(repository_history(q.get("full_name",[""])[0],home))
            if u.path=="/api/compare": return self.send_json(repository_compare(q.get("full_name",[""])[0],home))
            if u.path=="/api/manual-card": return self.send_json(get_repository_card(q.get("full_name",[""])[0],home))
            if u.path=="/api/acceptance/latest":
                with connect(home) as con:
                    row=con.execute("SELECT result_json FROM acceptance_runs ORDER BY run_at DESC LIMIT 1").fetchone()
                return self.send_json(json.loads(row[0]) if row else {"status":"HOLD","error":"No acceptance run recorded"})
            if u.path=="/api/receipts":
                files=sorted((home/"evidence"/"receipts").glob("*.json"),reverse=True)[:100]
                return self.send_json({"receipts":[json.loads(p.read_text()) for p in files]})
            if u.path.startswith("/exports/"):
                p=(home/"exports"/Path(u.path).name).resolve(); root=(home/"exports").resolve()
                if not str(p).startswith(str(root)+os.sep) or not p.exists(): return self.send_error(404)
                data=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","application/zip"); self.send_header("Content-Disposition",f'attachment; filename="{p.name}"'); self.send_header("Content-Length",str(len(data))); self.end_headers(); return self.wfile.write(data)
            if u.path.startswith("/manual-file/"):
                rel=u.path[len("/manual-file/"):]; p=(home/"manuals"/rel).resolve(); root=(home/"manuals").resolve()
                if not str(p).startswith(str(root)+os.sep) or not p.exists(): return self.send_error(404)
                data=p.read_bytes(); self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(str(p))[0] or "application/octet-stream"); self.send_header("Content-Length",str(len(data))); self.end_headers(); return self.wfile.write(data)
            path="index.html" if u.path in {"/","/index.html"} else u.path.lstrip("/")
            p=(STATIC/path).resolve()
            if not str(p).startswith(str(STATIC.resolve())+os.sep) or not p.exists(): return self.send_error(404)
            data=p.read_bytes(); self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(str(p))[0] or "application/octet-stream"); self.send_header("Cache-Control","no-cache"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        except Exception as e:
            return self.send_json({"status":"HOLD","error":str(e)},500)
    def do_POST(self):
        u=urlparse(self.path); home=self.server.home
        try:
            b=self.body()
            if u.path=="/api/refresh": return self.send_json(run_once(home,full_languages=b.get("full_languages",True) is not False))
            if u.path=="/api/github": return self.send_json(pull_inventory(home))
            if u.path=="/api/trending": return self.send_json(acquire(b.get("period","daily"),b.get("language") or None,home))
            if u.path=="/api/trending/sweep": return self.send_json(sweep(home,priority_only=bool(b.get("priority_only"))))
            if u.path=="/api/discover": return self.send_json(discover(home))
            if u.path=="/api/runtime/register": return self.send_json(register_runtime(b["path"],b.get("runtime_port"),b.get("health_endpoint"),b.get("source_status","SOURCE_PRESENT"),b.get("phone_status","DISCOVERED"),b.get("service_name"),home))
            if u.path=="/api/runtime/transition": return self.send_json(transition_runtime(b["path"],b["phone_status"],b.get("last_verified_operation"),home))
            if u.path=="/api/manuals": return self.send_json(generate_all(home))
            if u.path=="/api/export":
                r=export_everything(home); r["download_url"]="/exports/"+Path(r["zip"]).name; return self.send_json(r)
            if u.path=="/api/star": return self.send_json(set_star(b["full_name"],True,home))
            if u.path=="/api/unstar": return self.send_json(set_star(b["full_name"],False,home))
            if u.path=="/api/readme": return self.send_json(audit_readme(b["full_name"],home))
            if u.path=="/api/note":
                with connect(home) as con:
                    con.execute("INSERT OR REPLACE INTO notes(namespace,object_key,note,updated_at) VALUES(?,?,?,?)",(b.get("namespace","repo"),b["object_key"],b.get("note",""),utcnow()))
                receipt=write_receipt("note.save",inputs={"namespace":b.get("namespace","repo"),"object_key":b["object_key"]},result={"saved":True},home=home)
                return self.send_json({"status":"OK","receipt":receipt})
            if u.path=="/api/config/languages":
                cfg=load_config(home); cfg["languages"]=b["languages"]; save_config(cfg,home); write_receipt("config.languages.update",result={"count":len(cfg["languages"])},home=home); return self.send_json({"status":"OK","languages":cfg["languages"]})
            if u.path=="/api/workaround": return self.send_json(record_workaround(b["original_target"],b["original_blocker"],b["failed_gate"],b.get("attempt_history",[]),b.get("workaround_chain",[]),b.get("bypass_point"),b.get("behavioral_differences",[]),b.get("remaining_limitations",[]),b.get("rollback_path"),b.get("verification_result"),home))
            if u.path=="/api/acceptance": return self.send_json(run_acceptance(home,Path(b.get("source_dir")) if b.get("source_dir") else None,b.get("network_refresh",True)))
            if u.path=="/api/device-acceptance": return self.send_json(save_device_acceptance(b,home))
            if u.path=="/api/update/backup": return self.send_json(backup_state(home))
            if u.path=="/api/update/check": return self.send_json(check_update(Path(b.get("source_dir") or Path(__file__).resolve().parents[1])))
            if u.path=="/api/update/migrate": return self.send_json(migrate_database(home))
            if u.path=="/api/update/verify": return self.send_json(verify_source(Path(b.get("source_dir") or Path(__file__).resolve().parents[1])))
            if u.path=="/api/update/apply": return self.send_json(upgrade(Path(b.get("source_dir") or Path(__file__).resolve().parents[1]),home))
            if u.path=="/api/update/rollback": return self.send_json(rollback(Path(b["backup_path"]),home))
            if u.path=="/api/manual/predecessor": return self.send_json(import_predecessor(Path(b["path"]),b["manual_key"],home))
            return self.send_error(404)
        except Exception as e:
            return self.send_json({"status":"HOLD","error":str(e),"trace":traceback.format_exc(limit=3)},500)

def serve(home:Path=APP_HOME,bind=None,port=None):
    cfg=load_config(home); bind=bind or cfg.get("bind","127.0.0.1"); port=int(port or cfg.get("port",8765))
    httpd=ThreadingHTTPServer((bind,port),Handler); httpd.home=home
    write_receipt("runtime.health",result={"service":"local-http","bind":bind,"port":port,"state":"STARTING"},home=home)
    print(f"Lokivelli Radar: http://{bind}:{port}")
    try: httpd.serve_forever()
    finally: httpd.server_close()
