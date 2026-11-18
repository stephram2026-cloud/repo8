"""
Proof tests for the SQLAlchemy 1.3 -> 2.0 / Flask-SQLAlchemy 2 -> 3.1 answer key.

Every test goes through a real entry point (HTTP handler via the test client, a CLI
command via click's runner / a subprocess, or an Alembic migration's upgrade()) and
FAILS at the pin (f561a53d) because of the bug it documents.

R* = regression (passes on 93411450, the parent of the first upgrade commit, with
     SQLAlchemy 1.3.24 / Flask-SQLAlchemy 2.5.1 / sqlalchemy-searchable 1.2.0)
O* = old bug in the same area (fails before the upgrade as well)
"""
import glob
import importlib.util
import os
import subprocess
import sys
from urllib.parse import quote

from click.testing import CliRunner
from sqlalchemy import text
from sqlalchemy.orm import configure_mappers

from redash import models, settings
from redash.cli import manager
from redash.models import db
from redash.utils.configuration import ConfigurationContainer
from tests import BaseTestCase

# sqlalchemy-searchable attaches the DDL that creates the search trigger when the mappers
# are configured. BaseTestCase.setUp() creates the tables before anything configures them,
# so without this the first test of a process runs without a search trigger (at the pin and
# before the upgrade alike). `manage.py database create_tables` does the same thing.
configure_mappers()


class KeyTestCase(BaseTestCase):
    def status_of(self, method, path, **kwargs):
        """Status code of a request; an unhandled exception in the handler counts as a 500."""
        try:
            return self.make_request(method, path, **kwargs).status_code
        except Exception as e:  # TESTING=True propagates handler exceptions
            db.session.rollback()
            self.last_exception = e
            return 500


# --------------------------------------------------------------------------------------
# R1  `manage.py database reencrypt` aborts on the first row it cannot decrypt
# --------------------------------------------------------------------------------------
class TestR1ReencryptInvalidToken(KeyTestCase):
    def ciphertext(self, ds_id):
        q = text("SELECT encrypted_options FROM data_sources WHERE id = :id")
        return db.session.execute(q, {"id": ds_id}).scalar()

    def test_reencrypt_skips_rows_it_cannot_decrypt(self):
        runner = CliRunner()
        current = settings.DATASOURCE_SECRET_KEY

        # Row A ends up under another key (a first, partial key rotation)...
        ds_a = self.factory.create_data_source(name="a", options=ConfigurationContainer({"dbname": "a"}))
        db.session.commit()
        result = runner.invoke(manager, ["database", "reencrypt", current, "rotated-key"])
        self.assertFalse(result.exception, result.output)

        # ...and row B is created afterwards by the app, which still uses the current key.
        ds_b = self.factory.create_data_source(name="b", options=ConfigurationContainer({"dbname": "b"}))
        db.session.commit()
        before_b = self.ciphertext(ds_b.id)
        db.session.commit()

        # Rotating the current key must log row A ("Invalid Decryption Key for id ...")
        # and carry on with row B; that is what the try/except InvalidToken is for.
        result = runner.invoke(manager, ["database", "reencrypt", current, "rotated-key"])

        self.assertIsNone(result.exception, "reencrypt crashed: %r" % result.exception)
        self.assertNotEqual(before_b, self.ciphertext(ds_b.id), "row B was not re-encrypted")


# --------------------------------------------------------------------------------------
# R2  Query search: parentheses no longer group (sqlalchemy-searchable 2.2 parse_websearch)
# --------------------------------------------------------------------------------------
class TestR2SearchParentheses(KeyTestCase):
    def search(self, path, term):
        rv = self.make_request("get", "%s?q=%s" % (path, quote(term)))
        self.assertEqual(rv.status_code, 200, rv.data)
        return sorted(r["name"] for r in rv.json["results"])

    def test_parentheses_group_or_terms(self):
        for name in ("Revenue EU", "Revenue US", "Revenue APAC", "Costs US"):
            self.factory.create_query(name=name)

        # "revenue AND (eu OR us)". At the pin the parentheses are dropped and the term is
        # evaluated as "(revenue AND eu) OR us", which also returns "Costs US".
        self.assertEqual(["Revenue EU", "Revenue US"], self.search("/api/queries", "revenue (eu or us)"))

    def test_negated_group(self):
        for name in ("Sales final", "Sales draft", "Marketing test"):
            self.factory.create_query(name=name)

        # "sales AND NOT (draft OR test)" became "(sales AND NOT draft) OR test".
        self.assertEqual(["Sales final"], self.search("/api/queries/my", "sales -(draft or test)"))


# --------------------------------------------------------------------------------------
# R3  Query search: a term containing "scheme://" never matches any more
# --------------------------------------------------------------------------------------
class TestR3SearchUrl(KeyTestCase):
    def test_search_by_full_url(self):
        q = self.factory.create_query(name="Users API", query_text="url: https://api.example.com/v1/users")

        rv = self.make_request("get", "/api/queries?q=%s" % quote("https://api.example.com/v1/users", safe=""))

        self.assertEqual(rv.status_code, 200, rv.data)
        self.assertEqual([q.id], [r["id"] for r in rv.json["results"]])


# --------------------------------------------------------------------------------------
# R4  postgres:// database URLs (Heroku style DATABASE_URL) no longer start the app
# --------------------------------------------------------------------------------------
class TestR4PostgresScheme(KeyTestCase):
    def test_cli_starts_with_postgres_scheme_url(self):
        url = settings.SQLALCHEMY_DATABASE_URI
        self.assertTrue(url.startswith("postgresql://"), url)
        env = dict(os.environ, REDASH_DATABASE_URL=url.replace("postgresql://", "postgres://", 1))
        db.session.commit()

        proc = subprocess.run(
            [sys.executable, "manage.py", "org", "list"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=120,
        )

        self.assertEqual(0, proc.returncode, proc.stderr[-400:])
        self.assertIn("Slug: default", proc.stdout)


# --------------------------------------------------------------------------------------
# R5  Replaying the search-trigger migrations builds an *english* search vector
# --------------------------------------------------------------------------------------
def run_migration(revision, direction="upgrade"):
    # Same harness as tests/test_migrations.py at the pin.
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    (path,) = glob.glob(os.path.join("migrations", "versions", "%s_*.py" % revision))
    spec = importlib.util.spec_from_file_location("migration_%s" % revision, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with db.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            getattr(module, direction)()


class TestR5SearchTriggerMigration(KeyTestCase):
    def test_replayed_trigger_keeps_the_simple_regconfig(self):
        import sqlalchemy_searchable as ss

        vectorizers = dict(vars(ss.vectorizer))
        self.addCleanup(lambda: vars(ss.vectorizer).update(vectorizers))
        query = self.factory.create_query(name="Weekly revenue")
        user = self.factory.user
        db.session.commit()
        db.session.close()

        try:
            run_migration("6b5be7e0a0ef")
            with db.engine.begin() as connection:
                # the trigger installed by the migration fills search_vector on update
                connection.execute(text("UPDATE queries SET name = name"))
                source = connection.execute(
                    text("SELECT prosrc FROM pg_proc WHERE proname = 'queries_search_vector_update'")
                ).scalar()

            rv = self.make_request("get", "/api/queries?q=weekly", user=user)
            self.assertEqual(rv.status_code, 200, rv.data)
            found = [r["id"] for r in rv.json["results"]]
        finally:
            # don't leave the migration's trigger function behind for other test runs
            db.session.close()
            with db.engine.begin() as connection:
                connection.execute(text("DROP TRIGGER IF EXISTS queries_search_vector_trigger ON queries"))
                connection.execute(text("DROP FUNCTION IF EXISTS queries_search_vector_update()"))

        # At the pin the vector is 'revenu' / 'week' (english stemming) while the app
        # searches with the 'simple' configuration, so the full word no longer matches.
        self.assertEqual([query.id], found)
        self.assertIn("pg_catalog.simple", source)


# --------------------------------------------------------------------------------------
# O1  `manage.py users delete EMAIL --org ORG` always crashes
# --------------------------------------------------------------------------------------
class TestO1UsersDeleteOrg(KeyTestCase):
    def test_users_delete_with_org(self):
        self.factory.create_user(email="foobar@example.com")
        db.session.commit()

        result = CliRunner().invoke(manager, ["users", "delete", "foobar@example.com", "--org", self.factory.org.slug])

        self.assertIsNone(result.exception, "%r" % result.exception)
        self.assertIn("Deleted 1 users", result.output)


# --------------------------------------------------------------------------------------
# O2  Listing queries with a shared-dashboard API key is a 500
# --------------------------------------------------------------------------------------
class TestO2ApiKeyQueryList(KeyTestCase):
    def test_dashboard_api_key_can_list_queries_without_a_500(self):
        dashboard = self.factory.create_dashboard()
        rv = self.make_request("post", "/api/dashboards/%d/share" % dashboard.id)
        self.assertEqual(rv.status_code, 200, rv.data)
        key = rv.json["api_key"]

        try:
            rv = self.client.get("/%s/api/queries?api_key=%s" % (self.factory.org.slug, key))
            status = rv.status_code
        except Exception as e:
            self.fail("GET /api/queries with a dashboard API key raised %s: %s" % (type(e).__name__, str(e)[:200]))

        self.assertNotEqual(500, status)


# --------------------------------------------------------------------------------------
# O3  Multi-byte search by id ("id:123") is a 500
# --------------------------------------------------------------------------------------
class TestO3MultiByteSearchById(KeyTestCase):
    def test_id_term(self):
        admin = self.factory.create_admin()
        query = self.factory.create_query(name="日本語のクエリ")
        rv = self.make_request("post", "/api/settings/organization", user=admin, data={"multi_byte_search_enabled": True})
        self.assertEqual(rv.status_code, 200, rv.data)

        status = self.status_of("get", "/api/queries?q=id:%d" % query.id, user=admin)

        self.assertEqual(200, status, getattr(self, "last_exception", None))


# --------------------------------------------------------------------------------------
# O4  Adding a data source to a group twice breaks the group's data source pages
# --------------------------------------------------------------------------------------
class TestO4DuplicateGroupDataSource(KeyTestCase):
    def test_adding_twice_does_not_break_listing(self):
        admin = self.factory.create_admin()
        group = self.factory.create_group()
        ds = self.factory.create_data_source()
        db.session.commit()
        path = "/api/groups/%d/data_sources" % group.id

        self.assertEqual(200, self.status_of("post", path, user=admin, data={"data_source_id": ds.id}))
        self.status_of("post", path, user=admin, data={"data_source_id": ds.id})

        self.assertEqual(200, self.status_of("get", path, user=admin), getattr(self, "last_exception", None))
        self.assertEqual(
            200,
            self.status_of("post", "%s/%d" % (path, ds.id), user=admin, data={"view_only": True}),
            getattr(self, "last_exception", None),
        )


# --------------------------------------------------------------------------------------
# O5  A data source cannot be deleted once one of its queries moved to another one
# --------------------------------------------------------------------------------------
class TestO5DeleteDataSourceAfterQueryMoved(KeyTestCase):
    def test_delete(self):
        admin = self.factory.create_admin()
        ds1 = self.factory.create_data_source(group=self.factory.default_group)
        ds2 = self.factory.create_data_source(group=self.factory.default_group)
        query = self.factory.create_query(data_source=ds1, user=admin)
        result = self.factory.create_query_result(data_source=ds1, query_text=query.query_text, query_hash=query.query_hash)
        query.latest_query_data = result
        db.session.commit()

        rv = self.make_request("post", "/api/queries/%d" % query.id, user=admin, data={"data_source_id": ds2.id})
        self.assertEqual(rv.status_code, 200, rv.data)

        status = self.status_of("delete", "/api/data_sources/%d" % ds1.id, user=admin)

        self.assertEqual(204, status, getattr(self, "last_exception", None))


# --------------------------------------------------------------------------------------
# O6  A pending (invited) user that was granted an ACL permission cannot be deleted
# --------------------------------------------------------------------------------------
class TestO6DeletePendingUserWithPermission(KeyTestCase):
    def test_delete(self):
        admin = self.factory.create_admin()
        rv = self.make_request("post", "/api/users?no_invite=1", user=admin, data={"name": "p", "email": "p@example.com"})
        self.assertEqual(rv.status_code, 200, rv.data)
        user_id = rv.json["id"]
        query = self.factory.create_query(user=admin)
        rv = self.make_request(
            "post", "/api/queries/%d/acl" % query.id, user=admin, data={"access_type": "modify", "user_id": user_id}
        )
        self.assertEqual(rv.status_code, 200, rv.data)

        status = self.status_of("delete", "/api/users/%d" % user_id, user=admin)

        self.assertEqual(200, status, getattr(self, "last_exception", None))
