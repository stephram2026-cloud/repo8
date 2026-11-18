"""
Proof for: /api/jobs/<id> answers 500 for a job that is gone, and for a second cancel.

The test client runs with TESTING=True, so an unhandled exception in the view is re-raised here;
in a deployment the same exception is the "500 Internal Server Error" seen in the live transcripts.
"""
from redash import rq_redis_connection
from tests import BaseTestCase


class TestJobEndpoints(BaseTestCase):
    def setUp(self):
        super().setUp()
        rq_redis_connection.flushdb()

    def enqueue(self):
        query = self.factory.create_query()
        rv = self.make_request(
            "post",
            "/api/query_results",
            data={"data_source_id": query.data_source_id, "query": query.query_text, "max_age": 0},
        )
        return rv.json["job"]["id"]

    def test_get_expired_job(self):
        job_id = self.enqueue()
        rq_redis_connection.delete("rq:job:{}".format(job_id))  # what Redis does when the job's TTL runs out
        rv = self.make_request("get", "/api/jobs/{}".format(job_id))
        self.assertIn(rv.status_code, (200, 404))

    def test_cancel_expired_job(self):
        job_id = self.enqueue()
        rq_redis_connection.delete("rq:job:{}".format(job_id))
        rv = self.make_request("delete", "/api/jobs/{}".format(job_id))
        self.assertIn(rv.status_code, (200, 404))

    def test_cancel_twice(self):
        job_id = self.enqueue()
        self.assertEqual(self.make_request("delete", "/api/jobs/{}".format(job_id)).status_code, 200)
        rv = self.make_request("delete", "/api/jobs/{}".format(job_id))  # double click on Cancel
        self.assertEqual(rv.status_code, 200)
