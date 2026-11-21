from __future__ import annotations
import shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from .config import APP_HOME, ensure_layout
from .db import connect, migrate_connection
from .receipts import write_receipt

def _run(args,cwd=None,timeout=120):
    try:
        p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except Exception as e:return 127,'',str(e)

def backup_state(home:Path=APP_HOME):
    ensure_layout(home); stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'); dest=home/'backups'/f'state-{stamp}'; dest.mkdir(parents=True)
    for rel in ('db','config','manuals','evidence/receipts'):
        src=home/rel
        if src.exists(): shutil.copytree(src,dest/rel,dirs_exist_ok=True)
    r=write_receipt('backup.create',result={'path':str(dest)},home=home); return {'status':'OK','path':str(dest),'receipt':r}

def check_update(source_dir:Path):
    rc1,current,e1=_run(['git','rev-parse','HEAD'],source_dir); rc2,_,e2=_run(['git','fetch','origin'],source_dir); rc3,upstream,e3=_run(['git','rev-parse','@{u}'],source_dir)
    rc4,diff,e4=_run(['git','diff','--stat',current,upstream],source_dir) if rc1==0 and rc3==0 else (1,'','')
    status='OK' if rc1==rc2==rc3==0 else 'HOLD'
    return {'status':status,'current':current or None,'upstream':upstream or None,'compare':diff,'errors':[x for x in (e1,e2,e3,e4) if x]}

def migrate_database(home:Path=APP_HOME):
    try:
        with connect(home) as con:
            applied=migrate_connection(con)
            tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required={'repositories','stars_current','favorite_state','fork_state','trending_snapshots','runtime_current','events','manual_versions','acceptance_runs'}
        missing=sorted(required-tables)
        status='OK' if not missing else 'HOLD'
        r=write_receipt('database.migrate',result={'applied':applied,'missing_tables':missing},status=status,home=home)
        return {'status':status,'applied':applied,'missing_tables':missing,'receipt':r}
    except Exception as e:
        r=write_receipt('database.migrate',status='HOLD',errors=[str(e)],home=home)
        return {'status':'HOLD','error':str(e),'receipt':r}

def verify_source(source_dir:Path):
    checks=[]
    py=sys.executable
    rc,out,err=_run([py,'-m','compileall','-q','radar'],source_dir); checks.append({'name':'compileall','pass':rc==0,'output':out or err})
    rc2,out2,err2=_run([py,'-m','pytest','-q'],source_dir); checks.append({'name':'pytest','pass':rc2==0,'output':out2 or err2})
    return {'status':'OK' if all(x['pass'] for x in checks) else 'HOLD','checks':checks,'python':py}

def _http_live(url='http://127.0.0.1:8765/api/dashboard',timeout=4):
    try:
        with urlopen(url,timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False

def _start_fallback_processes(home:Path):
    ensure_layout(home); (home/'var').mkdir(parents=True,exist_ok=True)
    exe=Path(sys.executable).with_name('lokivelli-radar')
    if not exe.exists():
        return {'status':'HOLD','mode':'fallback','error':f'entry point missing: {exe}'}
    logs=home/'logs'; logs.mkdir(parents=True,exist_ok=True)
    try:
        http_log=(logs/'http-update-fallback.log').open('ab',buffering=0)
        sched_log=(logs/'scheduler-update-fallback.log').open('ab',buffering=0)
        hp=subprocess.Popen([str(exe),'--home',str(home),'serve'],stdout=http_log,stderr=subprocess.STDOUT,start_new_session=True)
        sp=subprocess.Popen([str(exe),'--home',str(home),'scheduler'],stdout=sched_log,stderr=subprocess.STDOUT,start_new_session=True)
        (home/'var'/'http-fallback.pid').write_text(str(hp.pid))
        (home/'var'/'scheduler-fallback.pid').write_text(str(sp.pid))
        time.sleep(2)
        ok=_http_live()
        return {'status':'OK' if ok else 'HOLD','mode':'nohup-equivalent-local-process','http_pid':hp.pid,'scheduler_pid':sp.pid,'health':'LIVE' if ok else 'HOLD'}
    except Exception as e:
        return {'status':'HOLD','mode':'fallback','error':str(e)}

def restart_service(home:Path=APP_HOME):
    rc,out,err=_run(['sv','restart','lokivelli-radar'])
    rc2,out2,err2=_run(['sv','restart','lokivelli-radar-scheduler'])
    if rc==0 and rc2==0:
        time.sleep(1)
        return {'status':'OK' if _http_live() else 'HOLD','mode':'runit','output':'\n'.join(x for x in (out,out2) if x),'error':'' if _http_live() else 'runit restarted but HTTP health is HOLD'}
    fallback=_start_fallback_processes(home)
    return {'status':fallback['status'],'mode':'workaround','direct_errors':[x for x in (err,err2) if x],'fallback':fallback,'error':fallback.get('error','') if fallback['status']!='OK' else ''}

def rollback(backup_path:Path,home:Path=APP_HOME):
    if not backup_path.exists(): return {'status':'HOLD','error':'backup path missing'}
    for rel in ('db','config','manuals','evidence/receipts'):
        src=backup_path/rel; dst=home/rel
        if src.exists():
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(src,dst)
    r=write_receipt('app.rollback',inputs={'backup':str(backup_path)},result={'restored':True},home=home)
    return {'status':'OK','receipt':r}

def upgrade(source_dir:Path,home:Path=APP_HOME):
    before=check_update(source_dir)
    if before['status']!='OK':
        r=write_receipt('app.update',status='HOLD',errors=before['errors'],result={'check':before},home=home); return {'status':'HOLD','receipt':r,'check':before}
    b=backup_state(home)
    rc,out,err=_run(['git','pull','--ff-only'],source_dir)
    if rc!=0:
        r=write_receipt('app.update',status='HOLD',errors=[err],result={'backup':b,'pull':out},home=home); return {'status':'HOLD','receipt':r,'rollback':b['path']}
    rc2,out2,err2=_run([sys.executable,'-m','pip','install','-e','.'],source_dir)
    migration=migrate_database(home) if rc2==0 else {'status':'HOLD','error':'install failed before migration'}
    verification=verify_source(source_dir) if rc2==0 and migration['status']=='OK' else {'status':'HOLD','checks':[{'name':'pip-install-or-migration','pass':False,'output':err2 or migration.get('error','migration failed')}]}
    restart=restart_service(home) if verification['status']=='OK' else {'status':'HOLD','error':'not restarted because verification failed'}
    status='OK' if verification['status']=='OK' and restart['status']=='OK' else 'HOLD'
    r=write_receipt('app.update',status=status,errors=[] if status=='OK' else [x for x in (err2,restart.get('error',''),migration.get('error','')) if x],result={'backup':b,'pull':out,'install':out2,'migration':migration,'verify':verification,'restart':restart},home=home)
    return {'status':status,'receipt':r,'rollback':b['path'],'migration':migration,'verify':verification,'restart':restart}
