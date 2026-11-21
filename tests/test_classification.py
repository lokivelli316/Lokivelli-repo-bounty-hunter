from radar.config import ensure_layout
from radar.db import connect
from radar.github_client import upsert_repository

def repo(repo_id=1, fork=False):
    return {'id':repo_id,'full_name':'lokivelli316/demo','owner':{'login':'lokivelli316'},'fork':fork,'visibility':'public','default_branch':'main','description':'x','language':'Python','topics':[],'archived':False}

def test_star_does_not_overwrite_owned(tmp_path):
    home=tmp_path/'h';ensure_layout(home)
    with connect(home) as con:
        upsert_repository(con,repo(),'owned')
        upsert_repository(con,repo(),'starred')
        r=con.execute("SELECT ownership,classification FROM repositories WHERE repo_id=1").fetchone()
        assert r['ownership']=='owned'
        assert r['classification']=='OWNED_ORIGINAL'
