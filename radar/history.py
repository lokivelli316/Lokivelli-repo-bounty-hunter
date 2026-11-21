from __future__ import annotations
import shutil
from datetime import datetime, timezone
from pathlib import Path
from .config import APP_HOME, ensure_layout
from .receipts import sha256_file, write_receipt

def import_predecessor(path:Path, manual_key:str, home:Path=APP_HOME):
    ensure_layout(home)
    if not path.exists() or not path.is_file(): raise FileNotFoundError(path)
    stamp=datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%SZ')
    dest=home/'manuals'/manual_key/'predecessors'/f'{stamp}_{path.name}'
    dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,dest)
    h=sha256_file(dest)
    r=write_receipt('manual.predecessor.import',inputs={'manual_key':manual_key,'source_name':path.name},source=str(dest),source_hash=h,result={'frozen_predecessor':str(dest)},home=home)
    return {'status':'OK','path':str(dest),'sha256':h,'receipt':r}
