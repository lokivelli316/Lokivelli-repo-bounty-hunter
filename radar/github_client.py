from __future__ import annotations
import json, os, subprocess, re
from pathlib import Path
import requests
from .db import connect, emit_event, rowdict
from .receipts import utcnow, write_receipt, sha256_bytes
from .config import APP_HOME

API = "https://api.github.com"
UA = "lokivelli-termux-github-radar/0.2"

class GitHubAuthError(RuntimeError): pass
class GitHubRequestError(RuntimeError): pass

def resolve_token(home: Path = APP_HOME) -> tuple[str|None, str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip(), "environment"
    token_file = home / "config" / "github_token"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip(), "local_file"
    try:
        p = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip(), "gh_cli"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None, "missing"

class GitHubClient:
    def __init__(self, home: Path = APP_HOME, token: str|None=None):
        self.home = home
        if token is None:
            token, source = resolve_token(home)
        else:
            source = "explicit"
        self.token = token
        self.token_source = source
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept":"application/vnd.github+json", "X-GitHub-Api-Version":"2022-11-28"})
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    @property
    def credential_state(self):
        return "PRESENT" if self.token else "MISSING"

    def _req(self, method, url, **kwargs):
        r = self.s.request(method, url, timeout=30, **kwargs)
        if r.status_code == 401:
            raise GitHubAuthError("GitHub authentication rejected (401)")
        if r.status_code >= 400:
            raise GitHubRequestError(f"GitHub {method} {url} -> {r.status_code}: {r.text[:500]}")
        return r

    def paginate(self, url: str, *, headers=None, params=None):
        items=[]; page=1
        params=dict(params or {})
        params.setdefault("per_page", 100)
        while url:
            r=self._req("GET", url, headers=headers, params=params if page==1 else None)
            payload=r.json()
            if not isinstance(payload, list):
                raise GitHubRequestError(f"Expected list from {url}")
            items.extend(payload)
            url = r.links.get("next", {}).get("url")
            page += 1
        return items

    def authenticated_user(self):
        if not self.token: raise GitHubAuthError("GitHub authentication: MISSING")
        return self._req("GET", f"{API}/user").json()

    def owned_repositories(self):
        if not self.token: raise GitHubAuthError("GitHub authentication: MISSING")
        return self.paginate(f"{API}/user/repos", params={"affiliation":"owner", "visibility":"all", "sort":"full_name", "per_page":100})

    def starred_repositories(self):
        if not self.token: raise GitHubAuthError("GitHub authentication: MISSING")
        headers={"Accept":"application/vnd.github.star+json", "X-GitHub-Api-Version":"2022-11-28"}
        return self.paginate(f"{API}/user/starred", headers=headers, params={"per_page":100})

    def star(self, full_name: str):
        if not self.token: raise GitHubAuthError("GitHub authentication: MISSING")
        owner, repo = full_name.split("/",1)
        r=self._req("PUT", f"{API}/user/starred/{owner}/{repo}", data=b"")
        return r.status_code in (204,304)

    def unstar(self, full_name: str):
        if not self.token: raise GitHubAuthError("GitHub authentication: MISSING")
        owner, repo = full_name.split("/",1)
        r=self._req("DELETE", f"{API}/user/starred/{owner}/{repo}")
        return r.status_code == 204

    def repository_detail(self, full_name: str):
        return self._req("GET", f"{API}/repos/{full_name}").json()

    def branch_head(self, full_name: str, branch: str):
        payload=self._req("GET", f"{API}/repos/{full_name}/branches/{branch}").json()
        return (payload.get("commit") or {}).get("sha")

    def readme(self, full_name: str):
        headers={"Accept":"application/vnd.github.raw+json", "X-GitHub-Api-Version":"2022-11-28"}
        r=self._req("GET", f"{API}/repos/{full_name}/readme", headers=headers)
        return r.text, r.url

def _repo_record(repo: dict, ownership: str, now: str) -> dict:
    owner = repo.get("owner",{}).get("login") or repo.get("full_name","").split("/")[0]
    parent = repo.get("parent") or {}
    license_obj=repo.get("license") or {}
    return {
        "repo_id": repo["id"], "full_name": repo["full_name"], "owner": owner,
        "classification": "FORK" if repo.get("fork") else ("OWNED_ORIGINAL" if ownership=="owned" else "THIRD_PARTY"),
        "ownership": ownership, "fork": int(bool(repo.get("fork"))),
        "upstream": parent.get("full_name"), "visibility": repo.get("visibility"),
        "default_branch": repo.get("default_branch"), "current_head": repo.get("_current_head"), "description": repo.get("description"),
        "primary_language": repo.get("language"), "topics_json": json.dumps(repo.get("topics") or []), "license_spdx": license_obj.get("spdx_id"),
        "created_at": repo.get("created_at"), "updated_at": repo.get("updated_at"), "pushed_at": repo.get("pushed_at"),
        "archived": int(bool(repo.get("archived"))), "homepage": repo.get("homepage"), "github_present": 1,
        "source_status": "SOURCE_PRESENT", "credential_state": "PRESENT", "last_repo_probe": now,
        "first_seen": now, "last_seen": now,
    }

def upsert_repository(con, repo: dict, ownership: str, evidence_ref: str|None=None):
    now=utcnow(); rec=_repo_record(repo, ownership, now)
    old=rowdict(con.execute("SELECT * FROM repositories WHERE repo_id=?",(rec["repo_id"],)).fetchone())
    cols=list(rec)
    if old:
        rec["first_seen"]=old["first_seen"]
        if old.get("ownership") == "owned" and ownership != "owned":
            rec["ownership"] = "owned"
            rec["classification"] = old.get("classification") or ("FORK" if rec["fork"] else "OWNED_ORIGINAL")
            rec["source_status"] = old.get("source_status") or rec["source_status"]
        changes=[]
        for field,event in [("full_name","REMOVED / RENAMED REPOSITORY"),("default_branch","DEFAULT BRANCH CHANGED"),("archived","ARCHIVED / UNARCHIVED"),("primary_language","LANGUAGE CHANGE"),("updated_at","REPOSITORY UPDATED")]:
            if old.get(field)!=rec.get(field): changes.append(event)
        assignments=",".join(f"{c}=?" for c in cols if c!="repo_id")
        con.execute(f"UPDATE repositories SET {assignments} WHERE repo_id=?", tuple(rec[c] for c in cols if c!="repo_id")+(rec["repo_id"],))
        for event in dict.fromkeys(changes): emit_event(con,event,rec["full_name"],old,rec,evidence_ref)
    else:
        con.execute(f"INSERT INTO repositories({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", tuple(rec[c] for c in cols))
        if ownership == "owned":
            emit_event(con,"NEW FORK" if rec["fork"] else "NEW OWNED REPOSITORY", rec["full_name"], None, rec, evidence_ref)
    if rec["fork"]:
        con.execute("INSERT OR IGNORE INTO fork_state(repo_id,upstream_status,local_modifications,adoption_state) VALUES(?,?,?,?)",
                    (rec["repo_id"],"KNOWN" if rec.get("upstream") else "UNKNOWN",None,"UNCLASSIFIED"))
        con.execute("UPDATE fork_state SET upstream_status=? WHERE repo_id=?",("KNOWN" if rec.get("upstream") else "UNKNOWN",rec["repo_id"]))
    return rec

def pull_inventory(home: Path = APP_HOME) -> dict:
    gh=GitHubClient(home)
    if not gh.token:
        r=write_receipt("github.inventory.pull", status="HOLD", errors=["GitHub authentication: MISSING"], result={"credential_state":"MISSING"}, home=home)
        return {"status":"HOLD","error":"GitHub authentication: MISSING","receipt":r}
    try:
        user=gh.authenticated_user(); owned=gh.owned_repositories(); starred=gh.starred_repositories(); now=utcnow()
        star_rows=[]; enrichment_warnings=[]
        owned_ids={repo["id"] for repo in owned}
        with connect(home) as con:
            previous_stars={r["repo_id"]:dict(r) for r in con.execute("SELECT * FROM stars_current")}
            previous_owned={r["repo_id"]:dict(r) for r in con.execute("SELECT * FROM repositories WHERE ownership='owned' AND github_present=1")}
            current_star_ids=set()
            for repo in owned:
                try:
                    if repo.get("fork"):
                        detail=gh.repository_detail(repo["full_name"])
                        repo["parent"]=detail.get("parent")
                        repo["license"]=detail.get("license") or repo.get("license")
                    if repo.get("default_branch"):
                        repo["_current_head"]=gh.branch_head(repo["full_name"],repo["default_branch"])
                except Exception as enrich_error:
                    enrichment_warnings.append(f"{repo.get('full_name')}: {enrich_error}")
                upsert_repository(con,repo,"owned")
            for rid,old in previous_owned.items():
                if rid not in owned_ids:
                    con.execute("UPDATE repositories SET github_present=0,last_repo_probe=? WHERE repo_id=?",(now,rid))
                    current={**old,"github_present":0,"last_repo_probe":now}
                    emit_event(con,"REMOVED / RENAMED REPOSITORY",old["full_name"],old,current)
            for pos,item in enumerate(starred,1):
                repo=item.get("repo",item); starred_at=item.get("starred_at")
                rec=upsert_repository(con,repo,"starred")
                current_star_ids.add(rec["repo_id"])
                star_rows.append((rec["repo_id"],pos,starred_at,now))
                con.execute("INSERT OR IGNORE INTO favorite_state(repo_id,first_seen_in_manual) VALUES(?,?)",(rec["repo_id"],now))
                old=previous_stars.get(rec["repo_id"])
                if old and old["star_position_current"] != pos:
                    emit_event(con,"STAR ORDER CHANGE",rec["full_name"],old,{"star_position_current":pos,"starred_at":starred_at})
                if not old: emit_event(con,"NEW STAR",rec["full_name"],None,{"star_position_current":pos,"starred_at":starred_at})
            for rid,old in previous_stars.items():
                if rid not in current_star_ids:
                    rr=con.execute("SELECT full_name FROM repositories WHERE repo_id=?",(rid,)).fetchone()
                    emit_event(con,"REMOVED STAR",rr[0] if rr else str(rid),old,None)
            con.execute("DELETE FROM stars_current")
            con.executemany("INSERT INTO stars_current(repo_id,star_position_current,starred_at,last_seen_in_stars) VALUES(?,?,?,?)",star_rows)
            sid=now.replace(":","").replace("+00:00","Z")
            con.executemany("INSERT INTO star_snapshots(snapshot_id,repo_id,position,starred_at,captured_at) VALUES(?,?,?,?,?)",[(sid,*x[:3],now) for x in star_rows])
            db_owned=con.execute("SELECT COUNT(*) FROM repositories WHERE ownership='owned' AND github_present=1").fetchone()[0]
            db_stars=con.execute("SELECT COUNT(*) FROM stars_current").fetchone()[0]
        digest=sha256_bytes(json.dumps({"owned":owned,"starred":starred},sort_keys=True).encode())
        stars_receipt=write_receipt("github.stars.pull",inputs={"account":user.get("login")},source="GitHub REST API",source_hash=digest,
                                    result={"star_count":len(starred),"db_star_count":db_stars,"pagination":"exhausted","star_timestamps_supported":True},warnings=enrichment_warnings,home=home)
        receipt=write_receipt("github.inventory.pull", inputs={"account":user.get("login")}, source="GitHub REST API", source_hash=digest,
                              result={"owned_count":len(owned),"db_owned_count":db_owned,"star_count":len(starred),"db_star_count":db_stars,"pagination":"exhausted","credential_state":"PRESENT","token_source":gh.token_source,"stars_receipt":stars_receipt["receipt_id"]}, warnings=enrichment_warnings, home=home)
        status="OK" if db_owned==len(owned) and db_stars==len(starred) else "HOLD"
        if status=="HOLD":
            receipt=write_receipt("github.inventory.count_verify",status="HOLD",errors=["Local current counts do not agree with retrieved GitHub counts"],result={"api_owned":len(owned),"db_owned":db_owned,"api_stars":len(starred),"db_stars":db_stars},home=home)
        return {"status":status,"user":user.get("login"),"owned_count":len(owned),"star_count":len(starred),"db_owned_count":db_owned,"db_star_count":db_stars,"receipt":receipt}
    except Exception as e:
        receipt=write_receipt("github.inventory.pull", status="HOLD", errors=[str(e)], result={"credential_state":gh.credential_state}, home=home)
        return {"status":"HOLD","error":str(e),"receipt":receipt}

def set_star(full_name:str, active:bool, home:Path=APP_HOME):
    gh=GitHubClient(home); op="repo.star" if active else "repo.unstar"
    try:
        ok=gh.star(full_name) if active else gh.unstar(full_name)
        receipt=write_receipt(op,inputs={"full_name":full_name},source="GitHub REST API",result={"applied":ok},home=home)
        refreshed=pull_inventory(home)
        return {"status":"OK" if ok and refreshed.get("status")=="OK" else "HOLD","applied":ok,"receipt":receipt,"inventory_refresh":refreshed}
    except Exception as e:
        receipt=write_receipt(op,inputs={"full_name":full_name},status="HOLD",errors=[str(e)],home=home)
        return {"status":"HOLD","error":str(e),"receipt":receipt}

def audit_readme(full_name:str, home:Path=APP_HOME):
    gh=GitHubClient(home)
    try:
        text,source=gh.readme(full_name)
        source_hash=sha256_bytes(text.encode())
        findings=[]; commands=[]
        for line in text.splitlines():
            st=line.strip()
            if st.startswith("#"):
                findings.append(st.lstrip("# ").strip())
            if re.search(r"\b(pkg|apt|pip|pipx|npm|pnpm|yarn|cargo|go|git clone|python|node|make|cmake|gradle|docker)\b",st,re.I):
                if st and len(st) < 400: commands.append(st)
        findings=findings[:100]; commands=commands[:200]
        with connect(home) as con:
            rr=con.execute("SELECT repo_id FROM repositories WHERE full_name=?",(full_name,)).fetchone()
            repo_id=rr[0] if rr else None
            con.execute("INSERT INTO readme_audits(repo_id,full_name,fetched_at,source_url,source_hash,status,content,findings_json,commands_json) VALUES(?,?,?,?,?,?,?,?,?)",
                        (repo_id,full_name,utcnow(),source,source_hash,"OK",text,json.dumps(findings),json.dumps(commands)))
            if repo_id:
                con.execute("INSERT OR IGNORE INTO favorite_state(repo_id,first_seen_in_manual) VALUES(?,?)",(repo_id,utcnow()))
                con.execute("UPDATE favorite_state SET readme_audit_state='AUDITED' WHERE repo_id=?",(repo_id,))
        receipt=write_receipt("github.readme.audit",inputs={"full_name":full_name},source=source,source_hash=source_hash,result={"findings":len(findings),"commands":len(commands)},home=home)
        return {"status":"OK","full_name":full_name,"source":source,"source_hash":source_hash,"findings":findings,"commands":commands,"content":text,"receipt":receipt}
    except Exception as e:
        receipt=write_receipt("github.readme.audit",inputs={"full_name":full_name},status="HOLD",errors=[str(e)],home=home)
        return {"status":"HOLD","full_name":full_name,"error":str(e),"receipt":receipt}
