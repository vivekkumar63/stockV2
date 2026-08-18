from scheduler import scheduler, register_jobs


def test_combination_analysis_job_registered():
    register_jobs()
    jobs = scheduler.get_jobs()
    job_ids = [j.id for j in jobs]
    assert "combination_analysis" in job_ids
