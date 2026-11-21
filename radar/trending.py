from __future__ import annotations
import re, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
from .config import APP_HOME, load_config, ensure_layout
from .db import connect, emit_event
from .receipts import utcnow, sha256_bytes, write_receipt

PARSER_VERSION="github-trending-html-v1"
UA="Mozilla/5.0 (Linux; Android 16) LokivelliRadar/0.1"

def _n(text):
    if text is None: return None
    t=text.strip().lower().replace(",","")
    m=re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([km]?)",t)
    if not m: return None
    v=float(m.group(1)); suffix=m.group(2)
    if suffix=="k": v*=1000
    elif suffix=="m": v*=1_000_000
    return int(v)

def parse_trending(html: str) -> tuple[list[dict], list[str]]:
    soup=BeautifulSoup(html,"html.parser")
    cards=[]; warnings=[]
    articles=soup.select("article.Box-row")
    for idx,article in enumerate(articles,1):
        a=article.select_one("h2 a")
        if not a or not a.get("href"):
            warnings.append(f"article {idx}: missing repository link")
            continue
        path=a["href"].strip("/")
        if path.count("/")!=1:
            warnings.append(f"article {idx}: malformed repository path {path!r}")
            continue
        desc_el=article.select_one("p")
        lang_el=article.select_one('[itemprop="programmingLanguage"]')
        star_el=article.select_one('a[href$="/stargazers"]')
        fork_el=article.select_one('a[href$="/forks"]')
        gain=None
        for span in article.find_all(["span","div"]):
            txt=" ".join(span.stripped_strings)
            if re.search(r"\bstars?\s+(today|this week|this month)\b",txt,re.I):
                gain=_n(txt); break
        cards.append({
            "position":idx,"full_name":path,
            "description":" ".join(desc_el.stripped_strings) if desc_el else None,
            "primary_language":lang_el.get_text(strip=True) if lang_el else None,
            "total_stars":_n(star_el.get_text(" ",strip=True)) if star_el else None,
            "forks":_n(fork_el.get_text(" ",strip=True)) if fork_el else None,
            "period_gain":gain,
        })
    if not articles: warnings.append("no article.Box-row nodes found")
    return cards,warnings

def trending_url(period:str, language:str|None=None) -> str:
    if period not in {"daily","weekly","monthly"}: raise ValueError("period must be daily, weekly, monthly")
    base="https://github.com/trending"
    if language: base += "/" + quote(language, safe="")
    return f"{base}?since={period}"

def latest_success(con, period, language=""):
    return con.execute("SELECT * FROM trending_sources WHERE period=? AND language_filter=? AND status='OK' ORDER BY captured_at DESC LIMIT 1",(period,language)).fetchone()

def acquire(period:str, language:str|None=None, home:Path=APP_HOME, session=None) -> dict:
    ensure_layout(home); language=language or ""; url=trending_url(period,language or None); s=session or requests.Session()
    captured=utcnow(); sid=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{period}-{language or 'all'}"
    status_code=None; raw_hash=None; raw_path=None; warnings=[]
    try:
        r=s.get(url,headers={"User-Agent":UA,"Accept":"text/html"},timeout=30)
        status_code=r.status_code; raw=r.content; raw_hash=sha256_bytes(raw)
        raw_dir=home/"evidence"/"trending"/datetime.now(timezone.utc).strftime("%Y-%m-%d")
        raw_dir.mkdir(parents=True,exist_ok=True)
        raw_path=raw_dir/f"{sid}.html"; raw_path.write_bytes(raw)
        if status_code!=200: raise RuntimeError(f"HTTP {status_code}")
        cards,warnings=parse_trending(r.text)
        if not cards: raise RuntimeError("parser produced zero repositories; refusing empty success")
        with connect(home) as con:
            prev=latest_success(con,period,language); prev_rows={}
            if prev:
                for rr in con.execute("SELECT * FROM trending_snapshots WHERE snapshot_id=?",(prev["snapshot_id"],)):
                    prev_rows[rr["full_name"]]=dict(rr)
            con.execute("INSERT INTO trending_sources(snapshot_id,requested_url,http_status,period,language_filter,captured_at,raw_html_hash,parser_version,parse_warnings_json,status,error,raw_path,repository_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid,url,status_code,period,language,captured,raw_hash,PARSER_VERSION,json.dumps(warnings),"OK",None,str(raw_path),len(cards)))
            for c in cards:
                repo=con.execute("SELECT repo_id FROM repositories WHERE full_name=?",(c["full_name"],)).fetchone()
                con.execute("INSERT INTO trending_snapshots(snapshot_id,period,language_filter,position,repo_id,full_name,description,primary_language,total_stars,forks,period_gain,captured_at,requested_url,source_hash,parser_version,stale) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                            (sid,period,language,c["position"],repo[0] if repo else None,c["full_name"],c["description"],c["primary_language"],c["total_stars"],c["forks"],c["period_gain"],captured,url,raw_hash,PARSER_VERSION))
                old=prev_rows.get(c["full_name"])
                if old is None:
                    emit_event(con,"NEW TRENDING APPEARANCE",c["full_name"],None,{"period":period,"language":language,"position":c["position"]},sid)
                elif old["position"]!=c["position"]:
                    emit_event(con,"TRENDING POSITION CHANGE",c["full_name"],{"position":old["position"]},{"position":c["position"]},sid)
        receipt=write_receipt("github.trending.pull",inputs={"period":period,"language":language},source=url,source_hash=raw_hash,
                              result={"snapshot_id":sid,"http_status":status_code,"repository_count":len(cards),"parser_version":PARSER_VERSION,"raw_path":str(raw_path)},warnings=warnings,home=home)
        write_receipt("github.trending.parse",inputs={"snapshot_id":sid},source=str(raw_path),source_hash=raw_hash,result={"repository_count":len(cards),"parser_version":PARSER_VERSION},warnings=warnings,home=home)
        return {"status":"OK","snapshot_id":sid,"url":url,"count":len(cards),"warnings":warnings,"receipt":receipt}
    except Exception as e:
        with connect(home) as con:
            prev=latest_success(con,period,language)
            con.execute("INSERT OR REPLACE INTO trending_sources(snapshot_id,requested_url,http_status,period,language_filter,captured_at,raw_html_hash,parser_version,parse_warnings_json,status,error,raw_path,repository_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sid,url,status_code,period,language,captured,raw_hash,PARSER_VERSION,json.dumps(warnings),"HOLD",str(e),str(raw_path) if raw_path else None,0))
            last=dict(prev) if prev else None
        receipt=write_receipt("github.trending.pull",inputs={"period":period,"language":language},source=url,source_hash=raw_hash,status="HOLD",warnings=warnings,
                              errors=[str(e)],result={"http_status":status_code,"raw_path":str(raw_path) if raw_path else None,"last_known_successful_snapshot":last},home=home)
        return {"status":"HOLD","url":url,"http_status":status_code,"error":str(e),"raw_path":str(raw_path) if raw_path else None,"last_known_successful_snapshot":last,"receipt":receipt}

def sweep(home:Path=APP_HOME, priority_only=False) -> dict:
    cfg=load_config(home); results=[]
    for period in ("daily","weekly","monthly"):
        results.append(acquire(period,None,home))
    langs=[x for x in cfg.get("languages",[]) if x.get("enabled")]
    if priority_only: langs=[x for x in langs if x.get("pinned")]
    for lang in langs:
        for period in ("daily","weekly","monthly"):
            results.append(acquire(period,lang["slug"],home))
    status="OK" if all(x["status"]=="OK" for x in results) else "HOLD"
    return {"status":status,"results":results}
