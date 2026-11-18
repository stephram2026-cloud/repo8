"""
Proof for: a query that is running when the worker is asked to stop (SIGTERM = deploy, `docker stop`,
supervisor restart) ends as a FAILED job with an empty error, and its lock is left behind.

Everything is real: the query is submitted through POST /api/query_results, executed by Redash's own rq worker
(`manage.py rq worker queries`, started as a child process), against a Postgres data source, and the worker receives SIGTERM
while `select pg_sleep(30)` is running.  rq's HerokuWorker then raises ShutDownImminentException inside the
job 6 seconds later.  In rq 1.x that was an `Exception`; QueryExecutor.run() turned it into a normal query
error, released the lock and (for scheduled queries) counted the failure.  In rq 2 it is a `BaseException`.
"""
import os
import signal
import subprocess
import sys
import time

from redash import redis_connection, rq_redis_connection
from redash.models import db
from redash.tasks import Queue
from redash.utils import json_dumps
from redash.utils.configuration import ConfigurationContainer
from tests import BaseTestCase


class TestWorkerShutdown(BaseTestCase):
    def setUp(self):
        super().setUp()
        rq_redis_connection.flushdb()

    def tearDown(self):
        Queue("queries", connection=rq_redis_connection).empty()
        super().tearDown()

    def test_query_interrupted_by_worker_shutdown(self):
        url = db.engine.url
        options = ConfigurationContainer.from_json(
            json_dumps({"host": url.host, "port": url.port or 5432, "user": url.username, "dbname": url.database})
        )
        ds = self.factory.create_data_source(type="pg", options=options, group=self.factory.default_group)
        db.session.commit()
        rv = self.make_request(
            "post", "/api/query_results", data={"data_source_id": ds.id, "query": "select pg_sleep(30)", "max_age": 0}
        )
        self.assertIn("id", rv.json.get("job", {}), rv.json)
        job_id = rv.json["job"]["id"]
        db.session.commit()

        # the real worker: `manage.py rq worker queries` (same Redis/Postgres settings as this test process)
        worker = subprocess.Popen([sys.executable, "manage.py", "rq", "worker", "queries"], env=os.environ.copy())
        try:
            # wait until the query is really running, then stop the worker the way a deploy does
            deadline = time.time() + 60
            while time.time() < deadline and self.make_request("get", "/api/jobs/" + job_id).json["job"]["status"] != 2:
                time.sleep(0.2)
            time.sleep(1)
            worker.send_signal(signal.SIGTERM)
            worker.wait(timeout=60)
        finally:
            if worker.poll() is None:
                worker.kill()

        job = self.make_request("get", "/api/jobs/" + job_id).json["job"]
        locks = redis_connection.keys("query_hash_job:*")
        print("\njob after worker shutdown:", job)
        print("locks left behind:", locks)
        self.assertEqual(job["status"], 4)
        self.assertNotEqual(job["error"], "", "the user gets a failed query with an empty error message")
        self.assertEqual(locks, [], "the query lock was not released")
