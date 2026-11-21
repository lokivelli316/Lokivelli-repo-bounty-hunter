from pathlib import Path
from radar.trending import parse_trending, trending_url

def test_parse_trending_sample():
    html=(Path(__file__).parent/"fixtures"/"trending_sample.html").read_text()
    rows,warnings=parse_trending(html)
    assert len(rows)==2
    assert rows[0]["full_name"]=="owner/repo-one"
    assert rows[0]["total_stars"]==12345
    assert rows[0]["period_gain"]==1234
    assert rows[1]["total_stars"]==9800
    assert not warnings

def test_url_encodes_language():
    assert "c%2B%2B" in trending_url("daily","c++")
