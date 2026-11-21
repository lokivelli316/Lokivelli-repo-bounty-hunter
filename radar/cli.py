from __future__ import annotations
import argparse, json
from pathlib import Path
from .config import APP_HOME, ensure_layout
from .server import serve
from .scheduler import run_once, daemon
from .github_client import pull_inventory
from .trending import acquire, sweep
from .termux import discover, register_runtime, transition_runtime
from .manuals import generate_all, get_repository_card
from .exporter import export_everything, restore_export
from .history import import_predecessor
from .update import backup_state, check_update, migrate_database, verify_source, upgrade, rollback
from .failure import record_workaround
from .acceptance import run_acceptance, save_device_acceptance

def out(x): print(json.dumps(x,indent=2,default=str))
def main():
    p=argparse.ArgumentParser(prog="lokivelli-radar"); p.add_argument("--home",type=Path,default=APP_HOME)
    s=p.add_subparsers(dest="cmd",required=True)
    sp=s.add_parser("serve"); sp.add_argument("--bind"); sp.add_argument("--port",type=int)
    rf=s.add_parser("refresh"); rf.add_argument("--priority-only",action="store_true")
    s.add_parser("github")
    tr=s.add_parser("trending"); tr.add_argument("--period",choices=["daily","weekly","monthly"],default="daily"); tr.add_argument("--language")
    sw=s.add_parser("sweep"); sw.add_argument("--priority-only",action="store_true")
    s.add_parser("discover"); s.add_parser("manuals"); s.add_parser("export")
    rr=s.add_parser("register-runtime"); rr.add_argument("path"); rr.add_argument("--port",type=int); rr.add_argument("--health"); rr.add_argument("--service-name")
    rt=s.add_parser("runtime-transition"); rt.add_argument("path"); rt.add_argument("phone_status"); rt.add_argument("--operation")
    mc=s.add_parser("manual-card"); mc.add_argument("full_name")
    ip=s.add_parser("import-predecessor"); ip.add_argument("manual_key"); ip.add_argument("path",type=Path)
    up=s.add_parser("update"); up.add_argument("action",choices=["check","backup","migrate","verify","apply","rollback"]); up.add_argument("--source-dir",type=Path,default=Path.cwd()); up.add_argument("--backup-path",type=Path)
    wa=s.add_parser("workaround"); wa.add_argument("record",type=Path,help="JSON record containing blocker/workaround fields")
    sch=s.add_parser("scheduler"); sch.add_argument("--interval",type=int,default=300)
    rs=s.add_parser("restore"); rs.add_argument("zip",type=Path)
    ac=s.add_parser("acceptance"); ac.add_argument("--no-network-refresh",action="store_true"); ac.add_argument("--source-dir",type=Path)
    da=s.add_parser("device-acceptance"); da.add_argument("record",type=Path,help="JSON booleans for portrait/landscape/touch/status/browser verification")
    a=p.parse_args(); ensure_layout(a.home)
    if a.cmd=="serve": return serve(a.home,a.bind,a.port)
    if a.cmd=="refresh": return out(run_once(a.home,not a.priority_only))
    if a.cmd=="github": return out(pull_inventory(a.home))
    if a.cmd=="trending": return out(acquire(a.period,a.language,a.home))
    if a.cmd=="sweep": return out(sweep(a.home,a.priority_only))
    if a.cmd=="discover": return out(discover(a.home))
    if a.cmd=="register-runtime": return out(register_runtime(a.path,a.port,a.health,service_name=a.service_name,home=a.home))
    if a.cmd=="runtime-transition": return out(transition_runtime(a.path,a.phone_status,a.operation,a.home))
    if a.cmd=="manual-card": return out(get_repository_card(a.full_name,a.home))
    if a.cmd=="manuals": return out(generate_all(a.home))
    if a.cmd=="export": return out(export_everything(a.home))
    if a.cmd=="scheduler": return daemon(a.home,a.interval)
    if a.cmd=="restore": return out(restore_export(a.zip,a.home))
    if a.cmd=="import-predecessor": return out(import_predecessor(a.path,a.manual_key,a.home))
    if a.cmd=="acceptance": return out(run_acceptance(a.home,a.source_dir,not a.no_network_refresh))
    if a.cmd=="device-acceptance": return out(save_device_acceptance(json.loads(a.record.read_text()),a.home))
    if a.cmd=="update":
        if a.action=="check": return out(check_update(a.source_dir))
        if a.action=="backup": return out(backup_state(a.home))
        if a.action=="migrate": return out(migrate_database(a.home))
        if a.action=="verify": return out(verify_source(a.source_dir))
        if a.action=="apply": return out(upgrade(a.source_dir,a.home))
        if a.action=="rollback":
            if not a.backup_path: p.error("update rollback requires --backup-path")
            return out(rollback(a.backup_path,a.home))
    if a.cmd=="workaround":
        d=json.loads(a.record.read_text())
        return out(record_workaround(d["original_target"],d["original_blocker"],d["failed_gate"],d.get("attempt_history",[]),d.get("workaround_chain",[]),d.get("bypass_point"),d.get("behavioral_differences",[]),d.get("remaining_limitations",[]),d.get("rollback_path"),d.get("verification_result"),a.home))

if __name__=="__main__": main()
