from scheduler import scheduler, JobIds


def test_scheduler_instance_exists():
    assert scheduler is not None


def test_job_ids_defined():
    assert hasattr(JobIds, "DAILY_EOD_UPDATE")
    assert hasattr(JobIds, "INTRADAY_SCAN")
    assert hasattr(JobIds, "WEEKLY_FUNDAMENTALS")
