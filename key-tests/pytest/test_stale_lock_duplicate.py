"""
Proof for: enqueue_query loses the per-query lock after it had to clear a stale lock.

Entry point: POST /api/query_results (the "Execute" button) and DELETE /api/jobs/<id> (the "Cancel" button).
Real Redis, real rq; nothing mocked.  The worker is not needed: jobs only have to be enqueued.
"""
from redash import redis_connection, rq_redis_connection
from redash.tasks import Queue
from tests import BaseTestCase


class TestStaleLockDuplicate(BaseTestCase):
    def setUp(self):
        super().setUp()
        rq_redis_connection.flushdb()
        self.queue = Queue("queries", connection=rq_redis_connection)

    def execute(self, query):
        rv = self.make_request(
            "post",
            "/api/query_results",
            data={"data_source_id": query.data_source_id, "query": query.query_text, "max_age": 0},
        )
        self.assertEqual(rv.status_code, 200)
        return rv.json["job"]["id"]

    def locks(self):
        return {k: redis_connection.get(k) for k in redis_connection.keys("query_hash_job:*")}

    def test_sanity_two_executes_share_one_job(self):
        # Baseline (passes): while a job is queued, a second Execute returns the same job.
        query = self.factory.create_query()
        first = self.execute(query)
        second = self.execute(query)
        self.assertEqual(first, second)
        self.assertEqual(self.queue.job_ids, [first])

    def test_execute_after_cancel_keeps_the_lock(self):
        query = self.factory.create_query()

        job1 = self.execute(query)
        self.assertEqual(list(self.locks().values()), [job1])

        # user cancels the queued query
        rv = self.make_request("delete", "/api/jobs/{}".format(job1))
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self.queue.job_ids, [])

        # ... and runs it again: the stale lock (cancelled job) is cleared and a new job is enqueued
        job2 = self.execute(query)
        self.assertNotEqual(job2, job1)
        print("\nlocks after job2 was enqueued:", self.locks())

        # a third Execute of the same query (second tab, other user, dashboard widget) must share job2
        job3 = self.execute(query)
        print("queue:", self.queue.job_ids)
        self.assertEqual(job3, job2, "same query was enqueued twice: no lock was written for job2")
        self.assertEqual(self.queue.job_ids, [job2])
