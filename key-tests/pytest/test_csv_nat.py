"""CSV / Excel data source: a date column that contains any blank cell makes the whole
query fail with "NaTType does not support strftime".

redash/query_runner/csv.py (and excel.py) apply the datetime->str conversion with
df[label].apply(lambda x: x.strftime("%Y-%m-%d %H:%M:%S")) *before* NaN/NaT are
replaced with None, so the missing value (NaT) blows up strftime.
"""
from unittest import TestCase, mock

from redash.query_runner.csv import CSV
from redash.query_runner.excel import Excel

# A perfectly ordinary CSV: one dated row, one row whose date is blank.
CSV_WITH_BLANK_DATE = b"event,when\nlogin,2020-01-01 10:00:00\nlogout,\n"


class TestCSVBlankDate(TestCase):
    def _run(self, runner_cls, module, content, query):
        with mock.patch("redash.query_runner.%s.requests_or_ssrf.get" % module) as get:
            get.return_value.content = content
            return runner_cls({}).run_query(query, None)

    def test_date_column_without_blanks_is_fine(self):
        data, error = self._run(CSV, "csv", b"event,when\nlogin,2020-01-01 10:00:00\n", "url: x\nparse_dates: [when]")
        self.assertIsNone(error)
        self.assertEqual("datetime", data["columns"][1]["type"])

    def test_blank_cell_in_date_column_fails_whole_query(self):
        data, error = self._run(CSV, "csv", CSV_WITH_BLANK_DATE, "url: x\nparse_dates: [when]")
        # Expected: the row is returned with a null date. Actual: the query errors out entirely.
        self.assertIsNone(error, "query failed: %r" % error)
        self.assertEqual([{"event": "login", "when": "2020-01-01 10:00:00"}, {"event": "logout", "when": None}],
                         data["rows"])
