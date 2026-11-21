from datetime import datetime, timezone
from radar.scheduler import cron_match, schedule_due

def test_cron_and_named_schedules():
    d=datetime(2026,11,23,8,0,tzinfo=timezone.utc)
    assert schedule_due('daily',d)
    assert schedule_due('weekly',d)
    assert cron_match('*/5 * * * *',d)
    assert not schedule_due('manual',d)
