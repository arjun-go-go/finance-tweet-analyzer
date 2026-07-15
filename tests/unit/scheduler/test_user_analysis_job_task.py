from uuid import uuid4

from app.scheduler import tasks


class _Session:
    closed = False

    def close(self):
        self.closed = True


def test_user_analysis_job_task_delegates_to_runner(monkeypatch):
    session = _Session()
    job_id = uuid4()
    seen = {}

    monkeypatch.setattr(tasks, "SessionLocal", lambda: session)

    def run_user_analysis_job(db, parsed_job_id, **kwargs):
        seen["db"] = db
        seen["job_id"] = parsed_job_id
        seen.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(tasks, "run_user_analysis_job", run_user_analysis_job)

    result = tasks.user_analysis_job_task.run(str(job_id))

    assert result == {"status": "completed"}
    assert seen["db"] is session
    assert seen["job_id"] == job_id
    assert seen["pipeline_version"] == "v1"
    assert seen["analyze_single_tweet"] is tasks.analyze_single_tweet
    assert seen["analyze_by_blogger"] is tasks.analyze_by_blogger
    assert session.closed is True
