from __future__ import annotations
import shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, ensure_layout
from .receipts import write_receipt

def _run(args,cwd=None,timeout=120):
    try:
        p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=timeout)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
    except Exception as e:return 127,'',str(e)

def backup_state(home:Path=APP_HOME):
    ensure_layout(home); stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); dest=home/'backups'/f'state-{stamp}'; dest.mkdir(parents=True)
    for rel in ('db','config','manuals','evidence/receipts'):
        src=home/rel
        if src.exists(): shutil.copytree(src,dest/rel,dirs_exist_ok=True)
    r=write_receipt('backup.create',result={'path':str(dest)},home=home); return {'status':'OK','path':str(dest),'receipt':r}

def check_update(source_dir:Path):
    rc1,current,e1=_run(['git','rev-parse','HEAD'],source_dir); rc2,_,e2=_run(['git','fetch','origin'],source_dir); rc3,upstream,e3=_run(['git','rev-parse','@{u}'],source_dir)
    rc4,diff,e4=_run(['git','diff','--stat',current,upstream],source_dir) if rc1==0 and rc3==0 else (1,'','')
    status='OK' if rc1==rc2==rc3==0 else 'HOLD'
    return {'status':status,'current':current or None,'upstream':upstream or None,'compare':diff,'errors':[x for x in (e1,e2,e3,e4) if x]}

def verify_source(source_dir:Path):
    checks=[]
    rc,out,err=_run(['python','-m','compileall','-q','radar'],source_dir); checks.append({'name':'compileall','pass':rc==0,'output':out or err})
    rc2,out2,err2=_run(['python','-m','pytest','-q'],source_dir); checks.append({'name':'pytest','pass':rc2==0,'output':out2 or err2})
    return {'status':'OK' if all(x['pass'] for x in checks) else 'HOLD','checks':checks}

def restart_service():
    rc,out,err=_run(['sv','restart','lokivelli-radar'])
    return {'status':'OK' if rc==0 else 'HOLD','output':out,'error':err}

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
    rc2,out2,err2=_run(['python','-m','pip','install','-e','.'],source_dir)
    verification=verify_source(source_dir) if rc2==0 else {'status':'HOLD','checks':[{'name':'pip-install','pass':False,'output':err2}]}
    restart=restart_service() if verification['status']=='OK' else {'status':'HOLD','error':'not restarted because verification failed'}
    status='OK' if verification['status']=='OK' and restart['status']=='OK' else 'HOLD'
    r=write_receipt('app.update',status=status,errors=[] if status=='OK' else [err2, restart.get('error','')],result={'backup':b,'pull':out,'install':out2,'verify':verification,'restart':restart},home=home)
    return {'status':status,'receipt':r,'rollback':b['path'],'verify':verification,'restart':restart}
