"""Connection regressions; engine construction opens no network connections."""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool, QueuePool

from database_config import database_connection_settings


class DatabaseConfigTest(unittest.TestCase):
    pooler = "aws-0-ap-southeast-2.pooler.supabase.com"

    def test_vercel_database_url_alone_uses_transaction_pooler_without_idle_clients(self):
        for port in ("", ":5432", ":6543"):
            with self.subTest(port=port):
                url, options = database_connection_settings(
                    f"postgres://postgres.project:secret@{self.pooler}{port}/postgres", {}, True)
                self.assertEqual(url.port, 6543)
                engine = create_engine(url, **options)
                self.assertIsInstance(engine.pool, NullPool)
                args, kwargs = engine.dialect.create_connect_args(url)
                self.assertEqual(kwargs["user"], "postgres.project")
                self.assertEqual(options["connect_args"]["connect_timeout"], 10)
                engine.dispose()

    def test_preserves_escaped_credentials_and_ssl_query(self):
        url, options = database_connection_settings(
            f"postgresql://postgres.project:a%40b%3Ac%2Fd%25@{self.pooler}:5432/postgres?sslmode=require&connect_timeout=17",
            {}, True)
        self.assertEqual(url.password, "a@b:c/d%")
        self.assertEqual(dict(url.query), {"sslmode": "require", "connect_timeout": "17"})
        self.assertNotIn("connect_args", options)
        self.assertEqual(url.port, 6543)

    def test_direct_database_keeps_host_and_port(self):
        for host in ("db.project.supabase.co", "postgres.example.com"):
            url, options = database_connection_settings(
                f"postgresql://postgres:secret@{host}:5432/postgres", {}, True)
            self.assertEqual((url.host, url.port, url.username), (host, 5432, "postgres"))
            self.assertIs(options["poolclass"], NullPool)

    def test_override_uses_project_username_from_original_host(self):
        url, options = database_connection_settings(
            "postgresql://postgres:secret@db.project.supabase.co:5432/postgres?sslmode=require",
            {"SUPABASE_POOLER_HOST": self.pooler, "SUPABASE_POOLER_PORT": "5432"}, True)
        self.assertEqual((url.host, url.port, url.username), (self.pooler, 6543, "postgres.project"))
        self.assertEqual(url.query["sslmode"], "require")
        self.assertIs(options["poolclass"], NullPool)

    def test_override_preserves_already_qualified_username(self):
        url, _ = database_connection_settings(
            "postgresql://postgres.project:secret@db.project.supabase.co/postgres",
            {"SUPABASE_POOLER_HOST": self.pooler}, True)
        self.assertEqual(url.username, "postgres.project")

    def test_custom_ports_and_non_supabase_hosts_are_not_rewritten(self):
        url, _ = database_connection_settings(
            f"postgresql://postgres:secret@{self.pooler}:7777/postgres", {}, True)
        self.assertEqual(url.port, 7777)
        url, _ = database_connection_settings(
            "postgresql://postgres:secret@db.example.com/postgres",
            {"SUPABASE_POOLER_HOST": "proxy.example.com", "SUPABASE_POOLER_PORT": "5432"}, True)
        self.assertEqual((url.host, url.port), ("proxy.example.com", 5432))

    def test_local_session_pooler_mode_and_direct_pool_are_preserved(self):
        url, options = database_connection_settings(
            f"postgresql://postgres.project:secret@{self.pooler}:5432/postgres", {}, False)
        self.assertEqual(url.port, 5432)
        self.assertIs(options["poolclass"], NullPool)
        url, options = database_connection_settings("postgresql://user:secret@localhost/postgres", {}, False)
        self.assertNotIn("poolclass", options)
        self.assertEqual(options["pool_recycle"], 300)

    def test_local_transaction_pooler_reuses_bounded_connections(self):
        configurations = (
            (f"postgresql://postgres.project:secret@{self.pooler}:6543/postgres", {}),
            ("postgresql://postgres:secret@db.project.supabase.co:5432/postgres",
             {"SUPABASE_POOLER_HOST": self.pooler, "SUPABASE_POOLER_PORT": "6543"}),
        )
        for raw_url, env in configurations:
            with self.subTest(override=bool(env)):
                url, options = database_connection_settings(raw_url, env, False)
                self.assertEqual(url.port, 6543)
                self.assertTrue(options["pool_pre_ping"])
                self.assertEqual(options["pool_recycle"], 300)
                self.assertEqual(options["max_overflow"], 2)
                engine = create_engine(url, **options)
                self.assertIsInstance(engine.pool, QueuePool)
                self.assertEqual(engine.pool.size(), 2)
                self.assertEqual(engine.pool.timeout(), 15)
                engine.dispose()

    def test_local_custom_poolers_and_implicit_session_port_keep_null_pool(self):
        configurations = (
            (f"postgresql://postgres.project:secret@{self.pooler}/postgres", {}),
            (f"postgresql://postgres.project:secret@{self.pooler}:7777/postgres", {}),
            ("postgresql://postgres:secret@db.project.supabase.co/postgres",
             {"SUPABASE_POOLER_HOST": "proxy.example.com", "SUPABASE_POOLER_PORT": "6543"}),
        )
        for raw_url, env in configurations:
            with self.subTest(override=bool(env)):
                _, options = database_connection_settings(raw_url, env, False)
                self.assertIs(options["poolclass"], NullPool)
                self.assertNotIn("pool_size", options)

    def test_sqlite_ignores_postgres_overrides_and_timeout(self):
        url, options = database_connection_settings(
            "sqlite:///:memory:", {"SUPABASE_POOLER_HOST": self.pooler}, True)
        engine = create_engine(url, **options)
        self.assertEqual(engine.url.database, ":memory:")
        self.assertNotIn("connect_args", options)
        self.assertNotIn("poolclass", options)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
