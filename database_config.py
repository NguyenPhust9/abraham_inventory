"""Database connection settings shared by local and serverless app startup."""
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, QueuePool


def database_connection_settings(raw_url, env, is_vercel=False):
    url = make_url(raw_url.replace("postgres://", "postgresql://", 1))
    options = {"pool_pre_ping": True}
    if url.get_backend_name() != "postgresql":
        return url, options

    override_host = env.get("SUPABASE_POOLER_HOST", "").strip()
    if override_host:
        original_host = (url.host or "").lower()
        user = url.username
        host_parts = original_host.split(".")
        if (len(host_parts) == 4 and host_parts[0] == "db"
                and host_parts[2:] == ["supabase", "co"] and user == "postgres"):
            user = f"postgres.{host_parts[1]}"
        url = url.set(host=override_host, username=user,
                      port=int(env.get("SUPABASE_POOLER_PORT", "5432")))

    # Detect the final URL, including configurations with DATABASE_URL alone.
    is_supabase_pooler = (url.host or "").lower().endswith(".pooler.supabase.com")
    if is_vercel and is_supabase_pooler and url.port in (None, 5432):
        url = url.set(port=6543)
    if not is_vercel and is_supabase_pooler and url.port == 6543:
        # Reuse a few local TLS connections. Transaction pooling releases server
        # connections after each transaction; session-mode clients stay unpooled.
        options.update(poolclass=QueuePool, pool_size=2, max_overflow=2,
                       pool_timeout=15, pool_recycle=300)
    elif is_vercel or is_supabase_pooler or override_host:
        # The external pooler owns pooling. Do not reserve idle clients in each
        # Vercel instance, including when no SUPABASE_POOLER_HOST override exists.
        options["poolclass"] = NullPool
    else:
        options["pool_recycle"] = 300

    if url.get_driver_name() in ("psycopg2", "psycopg") and "connect_timeout" not in url.query:
        options["connect_args"] = {"connect_timeout": 10}
    return url, options
