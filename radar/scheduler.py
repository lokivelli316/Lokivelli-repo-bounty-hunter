from __future__ import annotations
import time
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, load_config
from .github_client import pull_inventory
from .trending import acquire
from .termux import discover
from .manuals import generate_all
from .receipts import write_receipt
from .preservation import preserve_planned

def _cron_field(field,val):
    if field=='*': return True
    if field.startswith('*/'):
        try:return val%int(field[2:])==0
        except:return False
    vals=set()
    for part in field.split(','):
        try: vals.add(int(part))
        except: return False
    return val in vals

def cron_match(expr:str,now:datetime):
    parts=expr.split()
    if len(parts)!=5:return False
    minute,hour,dom,month,dow=parts
    cron_dow=(now.weekday()+1)%7
    return all((_cron_field(minute,now.minute),_cron_field(hour,now.hour),_cron_field(dom,now.day),_cron_field(month,now.month),_cron_field(dow,cron_dow)))

def schedule_due(spec:str,now:datetime):
    spec=(spec or 'manual').strip().lower()
    if spec=='manual': return False
    if spec=='daily': return now.hour==8 and now.minute==0
    if spec=='twice_daily': return now.hour in {8,20} and now.minute==0
    if spec=='weekly': return now.weekday()==0 and now.hour==8 and now.minute==0
    if spec=='monthly': return now.day==1 and now.hour==8 and now.minute==0
    return cron_match(spec,now)

def sweep_periods_for_language(home:Path,language:str|None):
    return [acquire(period,language,home) for period in ('daily','weekly','monthly')]

def run_once(home:Path=APP_HOME,full_languages=True):
    cfg=load_config(home); results={"github":pull_inventory(home),"trending":[],"termux":discover(home)}
    results['trending'] += sweep_periods_for_language(home,None)
    langs=[x for x in cfg.get('languages',[]) if x.get('enabled') and (full_languages or x.get('pinned'))]
    for x in langs: results['trending'] += sweep_periods_for_language(home,x['slug'])
    results['manuals']=generate_all(home)
    trend_ok=all(x.get('status')=='OK' for x in results['trending'])
    status='OK' if results['github'].get('status')=='OK' and results['termux'].get('status')=='OK' and results['manuals'].get('status')=='OK' and trend_ok else 'HOLD'
    write_receipt('scheduler.run',result={'status':status,'full_languages':full_languages,'trending_lanes':len(results['trending'])},status=status,home=home)
    return {'status':status,'results':results}

def daemon(home:Path=APP_HOME,interval_seconds=30):
    executed=set()
    while True:
        now=datetime.now(timezone.utc).replace(second=0,microsecond=0); cfg=load_config(home); minute_key=now.isoformat(); polling=cfg.get('polling',{})
        jobs=[]
        if schedule_due(polling.get('github_inventory','daily'),now): jobs.append(('github',None))
        if schedule_due(polling.get('trending_all','daily'),now): jobs.append(('trending-all',None))
        if schedule_due(polling.get('manual_delta','daily'),now): jobs.append(('manuals',None))
        if schedule_due(polling.get('complete_language_sweep','weekly'),now): jobs.append(('complete-language-sweep',None))
        if schedule_due(polling.get('preservation_sweep','manual'),now): jobs.append(('preservation-sweep',None))
        for x in cfg.get('languages',[]):
            if x.get('enabled') and schedule_due(x.get('polling','weekly'),now): jobs.append(('language',x['slug']))
        for job,arg in jobs:
            key=(minute_key,job,arg)
            if key in executed: continue
            try:
                if job=='github': pull_inventory(home)
                elif job=='trending-all': sweep_periods_for_language(home,None)
                elif job=='manuals': generate_all(home)
                elif job=='language': sweep_periods_for_language(home,arg)
                elif job=='complete-language-sweep':
                    for x in cfg.get('languages',[]):
                        if x.get('enabled'): sweep_periods_for_language(home,x['slug'])
                elif job=='preservation-sweep': preserve_planned(home)
            finally: executed.add(key)
        if now.hour==0 and now.minute==0: executed={x for x in executed if x[0].startswith(now.strftime('%Y-%m-%d'))}
        time.sleep(interval_seconds)
