from __future__ import annotations
import hashlib
import threading
from pathlib import Path
from urllib.request import urlopen

from radar.config import ensure_layout
from radar.db import connect
from radar.server import Handler, ThreadingHTTPServer, gui_inventory

HTML_SHA256="7402a883800abc651a1c1afc29bc3dfcb805f48bed3aaa16487a4add4c7a0e95"
MP4_SHA256="9dc48a94cf108c57b700d2615a8261f0f0968ebfc2196f341a5243b2b604155c"

def sha256(path:Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def test_canonical_gui_and_mp4_are_exact():
    root=Path(__file__).resolve().parents[1]
    index=root/"static"/"index.html"
    video=root/"static"/"assets"/"LOKIVELLI_REPO_BOUNTY_HUNTER_LOOP.mp4"
    wiring=root/"static"/"wiring.js"
    assert index.exists()
    assert wiring.exists()
    assert video.exists()
    assert sha256(index)==HTML_SHA256
    assert sha256(video)==MP4_SHA256
    text=index.read_text(encoding="utf-8")
    for route in (
        "/api/trending",
        "/api/github/inventory",
        "/api/runtime/discover",
        "/api/runtime/health",
        "/api/export/all",
    ):
        assert route in text

def test_gui_inventory_shape(tmp_path):
    home=tmp_path/"home"
    ensure_layout(home)
    with connect(home) as con:
        con.execute(
            """INSERT INTO repositories(
                repo_id,full_name,owner,ownership,fork,github_present,
                description,primary_language,first_seen,last_seen
            ) VALUES(1,'lokivelli316/demo','lokivelli316','owned',0,1,'demo repo','Python','x','x')"""
        )
        con.execute(
            "INSERT INTO stars_current(repo_id,star_position_current,starred_at,last_seen_in_stars) VALUES(1,1,'2026-11-21T00:00:00Z','2026-11-21T00:00:00Z')"
        )
        con.execute(
            "INSERT INTO events(event_type,object_key,at) VALUES('NEW STAR','lokivelli316/demo','2026-11-21T00:00:00Z')"
        )
    data=gui_inventory(home)
    assert data["status"]=="OK"
    assert len(data["stars"])==1
    assert len(data["owned"])==1
    assert data["stars"][0]["full_name"]=="lokivelli316/demo"
    assert data["stars"][0]["starred"] is True
    assert data["owned"][0]["owned"] is True
    assert data["snapshot"]["stars"]==1
    assert data["delta"][0]["description"]=="NEW STAR"

def test_http_health_and_runtime_wiring_injection(tmp_path):
    home=tmp_path/"home"
    ensure_layout(home)
    httpd=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    httpd.home=home
    thread=threading.Thread(target=httpd.serve_forever,daemon=True)
    thread.start()
    port=httpd.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz",timeout=3) as r:
            body=r.read().decode()
            assert r.status==200
            assert '"status": "LIVE"' in body or '"status":"LIVE"' in body
        with urlopen(f"http://127.0.0.1:{port}/",timeout=3) as r:
            body=r.read().decode("utf-8")
            assert '<script src="/wiring.js"></script>' in body
            assert "LOKIVELLI_REPO_BOUNTY_HUNTER_LOOP.mp4" in body
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)
