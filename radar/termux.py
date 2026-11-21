from __future__ import annotations
import json, os, subprocess, urllib.request
from pathlib import Path
from .config import APP_HOME, load_config
from .db import connect, emit_event
from .receipts import utcnow, write_receipt

MARKERS={
    "package.json":"Node.js/JavaScript",
    "pyproject.toml":"Python",
    "requirements.txt":"Python",
    "Cargo.toml":"Rust",
    "go.mod":"Go",
}

def _run(args,cwd=None,timeout=5):
    try:
        p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except (FileNotFoundError,subprocess.TimeoutExpired) as e:
        return 127,"",str(e)

def git_info(path:Path):
    def g(*args):
        rc,out,_=_run(["git","-C",str(path),*args]); return out if rc==0 else None
    dirty=None
    rc,out,_=_run(["git","-C",str(path),"status","--porcelain"])
    if rc==0: dirty=int(bool(out))
    return {"remote":g("remote","get-url","origin"),"branch":g("rev-parse","--abbrev-ref","HEAD"),"head":g("rev-parse","HEAD"),"dirty":dirty}

def detect_language(path:Path):
    found=[]
    for f,lang in MARKERS.items():
        if (path/f).exists(): found.append(lang)
    return ", ".join(dict.fromkeys(found)) or None

def build_presence(path:Path):
    present=[]
    for name in ("node_modules",".venv","venv","dist","build","target","__pycache__"):
        if (path/name).exists(): present.append(name)
    return ",".join(present) if present else None

def process_state(path:Path):
    rc,out,_=_run(["ps","-A","-o","pid,args"])
    if rc!=0: return "UNKNOWN"
    return "RUNNING" if str(path) in out else "NOT_SEEN"

def health_probe(url:str|None,timeout=3):
    if not url: return "UNKNOWN"
    try:
        with urllib.request.urlopen(url,timeout=timeout) as r:
            return "LIVE" if 200 <= r.status < 400 else f"HTTP_{r.status}"
    except Exception:
        return "HOLD"

def service_state(service_name:str|None):
    if not service_name: return "UNKNOWN"
    rc,out,err=_run(["sv","status",service_name])
    if rc==0:
        return out or "UP"
    return "UNKNOWN" if rc==127 else (err or out or "HOLD")

def _candidate_dirs(root:Path,max_depth=4):
    if not root.exists() or not root.is_dir(): return
    root_parts=len(root.parts)
    for base,dirs,files in os.walk(root):
        p=Path(base); depth=len(p.parts)-root_parts
        dirs[:] = [d for d in dirs if (d not in {"node_modules",".venv","venv","target","dist","build",".cache"} and not d.startswith(".")) or d==".git"]
        if ".git" in dirs or any(m in files for m in MARKERS) or "README.md" in files:
            yield p
            if ".git" in dirs: dirs[:] = [d for d in dirs if d != ".git"]
        if depth >= max_depth: dirs[:] = []

def discover(home:Path=APP_HOME):
    cfg=load_config(home); now=utcnow(); found={}; timeout=cfg.get("health_timeout_seconds",3)
    registry_file=home/"config"/"runtime_registry.json"
    registry={}
    if registry_file.exists():
        try: registry=json.loads(registry_file.read_text())
        except Exception: registry={}
    for root_s in cfg.get("termux_roots",[]):
        root=Path(root_s)
        for path in _candidate_dirs(root) or []:
            key=str(path.resolve())
            if key in found: continue
            gi=git_info(path) if (path/".git").exists() else {"remote":None,"branch":None,"head":None,"dirty":None}
            reg=registry.get(key,{})
            hurl=reg.get("health_endpoint")
            hstate=health_probe(hurl,timeout)
            pstate=process_state(path)
            svc=service_state(reg.get("service_name")) if reg.get("service_name") else reg.get("service_manager_state","UNKNOWN")
            phone_status="LIVE" if hstate=="LIVE" else ("DISCOVERED" if pstate in {"RUNNING","NOT_SEEN"} else "UNKNOWN")
            last_launch=now if hstate=="LIVE" else reg.get("last_successful_launch")
            last_op="health_probe:LIVE" if hstate=="LIVE" else reg.get("last_verified_operation")
            found[key]={
                "path":key,**gi,"runtime_language":detect_language(path),"build_presence":build_presence(path),
                "runtime_port":reg.get("runtime_port"),"process_state":pstate,"health_endpoint":hurl,"health_state":hstate,
                "service_manager_state":svc,"tunnel_state":reg.get("tunnel_state","UNKNOWN"),
                "source_status":reg.get("source_status","SOURCE_PRESENT"),"phone_status":phone_status,
                "last_successful_launch":last_launch,"last_verified_operation":last_op,"probed_at":now,
            }
    with connect(home) as con:
        previous={r["path"]:dict(r) for r in con.execute("SELECT * FROM runtime_current")}
        for key,rec in found.items():
            old=previous.get(key)
            if not old: emit_event(con,"PHONE INSTALL DISCOVERED",key,None,rec)
            elif old.get("phone_status")!=rec.get("phone_status") or old.get("health_state")!=rec.get("health_state"):
                emit_event(con,"RUNTIME STATE CHANGE",key,old,rec)
            cols=list(rec)
            con.execute(f"INSERT OR REPLACE INTO runtime_current({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",tuple(rec[c] for c in cols))
        for key,old in previous.items():
            if key not in found:
                missing={**old,"process_state":"MISSING","health_state":"HOLD","phone_status":"HOLD","probed_at":now}
                con.execute("UPDATE runtime_current SET process_state='MISSING',health_state='HOLD',phone_status='HOLD',probed_at=? WHERE path=?",(now,key))
                emit_event(con,"PHONE INSTALL MISSING",key,old,missing)
    live=sum(1 for r in found.values() if r["health_state"]=="LIVE")
    health_receipt=write_receipt("runtime.health",inputs={"runtime_count":len(found)},source="local Termux runtime probes",result={"live":live,"hold":sum(1 for r in found.values() if r['health_state']=='HOLD'),"unknown":sum(1 for r in found.values() if r['health_state']=='UNKNOWN')},home=home)
    receipt=write_receipt("termux.discovery",inputs={"roots":cfg.get("termux_roots",[])},source="local Termux filesystem",result={"discovered":len(found),"runtime_health_receipt":health_receipt["receipt_id"]},home=home)
    return {"status":"OK","discovered":len(found),"items":list(found.values()),"receipt":receipt}

def register_runtime(path:str, runtime_port=None, health_endpoint=None, source_status="SOURCE_PRESENT", phone_status="DISCOVERED", service_name=None, home:Path=APP_HOME):
    cfg_path=home/"config"/"runtime_registry.json"; cfg_path.parent.mkdir(parents=True,exist_ok=True)
    try: reg=json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    except Exception: reg={}
    key=str(Path(path).expanduser().resolve())
    old=reg.get(key,{})
    reg[key]={**old,"runtime_port":runtime_port,"health_endpoint":health_endpoint,"source_status":source_status,"phone_status":phone_status,"service_name":service_name or old.get("service_name")}
    tmp=cfg_path.with_suffix('.tmp'); tmp.write_text(json.dumps(reg,indent=2,sort_keys=True)); os.replace(tmp,cfg_path)
    receipt=write_receipt("runtime.register",inputs={"path":key},result=reg[key],home=home)
    return {"status":"OK","path":key,"registry":reg[key],"receipt":receipt}

def transition_runtime(path:str, phone_status:str, last_verified_operation=None, home:Path=APP_HOME):
    allowed={"UNKNOWN","DISCOVERED","INSTALLING","CONFIGURING","WIRING","AUTHENTICATING","VERIFYING","LIVE","DEGRADED","HOLD","REPAIRING","RETRYING","BYPASS_VERIFYING","BYPASS_LIVE"}
    if phone_status not in allowed:
        return {"status":"HOLD","error":f"invalid phone status {phone_status}"}
    if phone_status in {"STAGED","UNCONFIGURED"}:
        return {"status":"HOLD","error":f"{phone_status} cannot be accepted as a completed phone deployment state"}
    key=str(Path(path).expanduser().resolve()); now=utcnow()
    with connect(home) as con:
        row=con.execute("SELECT * FROM runtime_current WHERE path=?",(key,)).fetchone()
        if not row: return {"status":"HOLD","error":"runtime path not discovered"}
        old=dict(row)
        last_launch=now if phone_status in {"LIVE","BYPASS_LIVE"} else old.get("last_successful_launch")
        con.execute("UPDATE runtime_current SET phone_status=?,last_successful_launch=?,last_verified_operation=?,probed_at=? WHERE path=?",(phone_status,last_launch,last_verified_operation or old.get("last_verified_operation"),now,key))
        current={**old,"phone_status":phone_status,"last_successful_launch":last_launch,"last_verified_operation":last_verified_operation or old.get("last_verified_operation"),"probed_at":now}
        emit_event(con,"RUNTIME STATE CHANGE",key,old,current)
    receipt=write_receipt("runtime.transition",inputs={"path":key},result=current,home=home)
    return {"status":"OK","runtime":current,"receipt":receipt}
