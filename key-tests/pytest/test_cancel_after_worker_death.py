"""
Proof for: a running query whose worker died cannot be cancelled for about a minute
(DELETE /api/jobs/<id> raises -> HTTP 500).

Real pieces: POST /api/query_results, `manage.py rq worker queries` as a child process, a Postgres data source.
The worker and its work horse are SIGKILLed while `select pg_sleep(300)` runs (OOM kill, node loss, `docker kill`).
70 seconds later the user presses Cancel.

rq 2 keeps one "execution" per running job: the hash rq:execution:<job>:<id> lives 65 s after the worker's last
heartbeat, but its id stays in the sorted set rq:executions:<job> for 60 s longer.  Job.cancel() of a started job
loads every listed execution and raises ValueError for the one whose hash is gone.  rq 1.x simply removed the
job from the started registry.  (Takes ~80 s to run.)
"""
import os
import signal
import subprocess
import sys
import time

from redash import rq_redis_connection
from redash.models import db
from redash.tasks import Queue
from redash.utils import json_dumps
from redash.utils.configuration import ConfigurationContainer
from tests import BaseTestCase


def children_of(pid):
    result = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open("/proc/{}/stat".format(entry)) as f:
                    if int(f.read().rsplit(")", 1)[1].split()[1]) == pid:
                        result.append(int(entry))
            except OSError:
                pass
    return result


class TestCancelAfterWorkerDeath(BaseTestCase):
    def setUp(self):
        super().setUp()
        rq_redis_connection.flushdb()

    def tearDown(self):
        Queue("queries", connection=rq_redis_connection).empty()
        super().tearDown()

    def test_cancel_query_of_dead_worker(self):
        url = db.engine.url
        options = ConfigurationContainer.from_json(
            json_dumps({"host": url.host, "port": url.port or 5432, "user": url.username, "dbname": url.database})
        )
        ds = self.factory.create_data_source(type="pg", options=options, group=self.factory.default_group)
        db.session.commit()
        rv = self.make_request(
            "post", "/api/query_results", data={"data_source_id": ds.id, "query": "select pg_sleep(300)", "max_age": 0}
        )
        job_id = rv.json["job"]["id"]

        worker = subprocess.Popen([sys.executable, "manage.py", "rq", "worker", "queries"], env=os.environ.copy())
        try:
            deadline = time.time() + 60
            while time.time() < deadline and self.make_request("get", "/api/jobs/" + job_id).json["job"]["status"] != 2:
                time.sleep(0.2)
            time.sleep(6)  # let the worker send at least one heartbeat for the running job
            for pid in children_of(worker.pid) + [worker.pid]:  # the work horse, then the worker itself
                os.kill(pid, signal.SIGKILL)
            worker.wait()
        finally:
            if worker.poll() is None:
                worker.kill()

        self.assertEqual(self.make_request("get", "/api/jobs/" + job_id).json["job"]["status"], 2)  # "executing"
        time.sleep(70)

        executions = [e.decode() for e in rq_redis_connection.zrange("rq:executions:" + job_id, 0, -1)]
        print("\nrq:executions:<job> =", executions, "| execution hashes present:",
              [bool(rq_redis_connection.exists("rq:execution:{}:{}".format(job_id, e))) for e in executions])
        rv = self.make_request("delete", "/api/jobs/" + job_id)  # user presses Cancel on the stuck query
        self.assertEqual(rv.status_code, 200)
