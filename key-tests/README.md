# Proofs for the 21 graded bugs

Repository: `getredash/redash` at `f561a53dc55eeb3f20615be951560dc78bb23f4c` (upstream master).

Every pytest here asserts the correct behaviour, so **a failing test at the pinned commit means the bug is reproduced**.
Tests named `control`, `sanity`, `plain` or `without_blanks` are controls and pass.

## How to run

pytest proofs (need the repo's normal test setup: Postgres and Redis, see the repo's `compose.yaml` / `tests/__init__.py`):

    cp -r key-tests/pytest  <redash checkout>/tests/zz_key
    pytest tests/zz_key -q -s

Two of them (`test_worker_shutdown.py`, `test_cancel_after_worker_death.py`) start a real `manage.py rq worker queries`
process and take about 100 seconds together.

Live scripts (`live/`) talk to a running server and worker over HTTP. `stack.sh` shows how the containers were started
(set `LABDIR` to your checkout), `rd.py` is the small HTTP helper (set `RD_KEY` to an admin API key). `outputs/` holds the
captured output at the pin (`*-current.log`, `pytest-zz_key.log`) and on the libraries before the upgrades (`*-pre.log`).

## Criterion → proof

| # | Bug | Proof |
|---|---|---|
| 1 | `database reencrypt` stops on the first row it cannot decrypt | `pytest/test_key_sqla.py::TestR1ReencryptInvalidToken` |
| 2 | Search ignores parentheses | `pytest/test_key_sqla.py::TestR2SearchParentheses` |
| 3 | Search term with `scheme://` returns nothing | `pytest/test_key_sqla.py::TestR3SearchUrl` |
| 4 | `postgres://` database URL fails at start-up | `pytest/test_key_sqla.py::TestR4PostgresScheme` |
| 5 | Worker SIGTERM during a query: failed job with empty error | `pytest/test_worker_shutdown.py`, `live/term.sh`, `outputs/sigterm-query-current.log` vs `-pre.log` |
| 6 | Cancel returns 500 after the worker died | `pytest/test_cancel_after_worker_death.py`, `live/canceldead.sh` + `live/p8.py`, `outputs/canceldead-current.log` vs `-pre.log` |
| 7 | `users delete --org` ArgumentError | `pytest/test_key_sqla.py::TestO1UsersDeleteOrg` |
| 8 | `GET /api/queries` with a dashboard API key returns 500 | `pytest/test_key_sqla.py::TestO2ApiKeyQueryList` |
| 9 | Multi-byte search `id:123` returns 500 | `pytest/test_key_sqla.py::TestO3MultiByteSearchById` |
| 10 | Data source cannot be deleted after a query was moved | `pytest/test_key_sqla.py::TestO5DeleteDataSourceAfterQueryMoved` |
| 11 | Pending user with an access permission cannot be deleted | `pytest/test_key_sqla.py::TestO6DeletePendingUserWithPermission` |
| 12 | Same query runs twice after a stale lock was cleared | `pytest/test_stale_lock_duplicate.py::test_execute_after_cancel_keeps_the_lock`, `live/p7.py`, `outputs/live-stale-lock-current.log` |
| 13 | "Test Connection" says success for an unreachable data source | `live/p9.py`, `outputs/test-connection-exasol-current.log` |
| 14 | Cancel after finish turns the job into "Query cancelled by user." | `live/p2.py` part B, `outputs/live-cancel-flows-current.log` |
| 15 | `GET`/`DELETE /api/jobs/<id>` 500 for an expired job | `pytest/test_job_endpoints.py::test_get_expired_job`, `::test_cancel_expired_job` |
| 16 | Second cancel returns 500 | `pytest/test_job_endpoints.py::test_cancel_twice` |
| 17 | CSRF not checked for logged-in session users | `pytest/test_csrf_session.py::test_session_user_post_without_token_is_rejected` |
| 18 | JSON data source origin check bypass | `pytest/test_json_origin_bypass.py::test_backslash_url_reaches_attacker_with_credentials` |
| 19 | Numeric NaN in a result fails the job | `pytest/test_pg_nan_serialization.py::test_numeric_nan_crashes_the_job` |
| 20 | Time with timezone in a result fails the job | `pytest/test_pg_nan_serialization.py::test_timetz_crashes_the_job` |
| 21 | Blank cell in a CSV/Excel date column fails the query | `pytest/test_csv_nat.py::test_blank_cell_in_date_column_fails_whole_query` (CSV; the Excel runner has the same lines) |

`test_key_sqla.py` also holds two test classes that are not graded (`TestR5...`: low reach, `TestO4...`: already reported upstream).

Criteria 1 to 4 passed when the same tests ran with the SQLAlchemy 1.3 package set from before the upgrades. Criteria 5 and 6 pass on the old libraries too (`outputs/pytest-zz_key-pre.log`, `*-pre.log`). Criteria 7 to 21 fail on both.
