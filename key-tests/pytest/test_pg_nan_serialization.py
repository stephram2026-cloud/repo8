"""A PostgreSQL query that returns a numeric NaN (or +/-Infinity) makes result
serialization crash, so the query job fails instead of returning the result.

redash.utils.JSONEncoder.default converts decimal.Decimal with float(o); for
Decimal('NaN') that is a Python nan, and json_dumps(..., allow_nan=False) then raises.
_sanitize_data only rewrites real float nan/inf, not Decimal, so it never sees it.
Reached through the real execute_query task that stores every query result as JSONText.
"""
from unittest.mock import Mock, patch

from tests import BaseTestCase
from redash.tasks.queries.execution import execute_query


class TestNumericNaNResult(BaseTestCase):
    def _run(self, sql):
        ds = self.factory.create_data_source(
            group=self.factory.default_group,
            type="pg",
            options={"host": "postgres", "user": "postgres", "dbname": "tests"},
        )
        # In production execute_query always runs inside an rq job.
        job = Mock()
        job.id = "job-1"
        with patch("redash.tasks.queries.execution.get_current_job", return_value=job):
            return execute_query(sql, ds.id, {"Username": "t", "Query ID": "adhoc"})

    def test_plain_numeric_is_fine(self):
        result_id = self._run("SELECT 1.5::numeric AS a")
        self.assertIsInstance(result_id, int)

    def test_numeric_nan_crashes_the_job(self):
        # A legitimate value a Postgres query can return (e.g. AVG over no rows, 'NaN'::numeric).
        result_id = self._run("SELECT 'NaN'::numeric AS a")
        self.assertIsInstance(result_id, int)

    def test_timetz_crashes_the_job(self):
        # A `time with time zone` column also breaks serialization
        # ("JSON can't represent timezone-aware times.").
        result_id = self._run("SELECT '10:00:00+02'::timetz AS a")
        self.assertIsInstance(result_id, int)
