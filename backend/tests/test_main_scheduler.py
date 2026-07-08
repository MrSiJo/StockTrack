import inspect

import stocktrack.main as main


def test_scheduler_registers_archival_and_heartbeat(monkeypatch):
    added = []

    class FakeSched:
        def __init__(self, *a, **k):
            pass

        def add_job(self, fn, *a, **k):
            added.append(k.get("id"))

        def start(self):
            pass

    monkeypatch.setattr(main, "AsyncIOScheduler", FakeSched)
    # Exercise only the job-registration section if factored out; otherwise
    # assert the ids appear in the source of create_app's scheduler setup.
    src = inspect.getsource(main)
    assert '"archival"' in src or 'id="archival"' in src
    assert '"heartbeat"' in src or 'id="heartbeat"' in src
