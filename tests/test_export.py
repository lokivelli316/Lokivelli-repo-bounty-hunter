from pathlib import Path
import zipfile
from radar.config import ensure_layout
from radar.db import connect
from radar.manuals import generate_all
from radar.exporter import export_everything, restore_export

def test_export_and_restore(tmp_path):
    home=tmp_path/"home"; ensure_layout(home)
    with connect(home) as con:
        con.execute("INSERT INTO repositories(repo_id,full_name,owner,ownership,fork,first_seen,last_seen) VALUES(1,'lokivelli316/demo','lokivelli316','owned',0,'x','x')")
    generate_all(home); ex=export_everything(home)
    zp=Path(ex["zip"]); assert zp.exists()
    with zipfile.ZipFile(zp) as z:
        names=set(z.namelist()); assert "MANIFEST.json" in names and "SHA256SUMS" in names
        assert "manuals/owned_repo_termux.pdf" in names
    clean=tmp_path/"clean"; restore_export(zp,clean)
    with connect(clean) as con:
        assert con.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]==1
