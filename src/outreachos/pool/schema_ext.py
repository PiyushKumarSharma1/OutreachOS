"""Extended schema for v0.4 backend systems. Applied by PoolStore.ensure_ext_schema()."""

EXT_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    plan TEXT NOT NULL DEFAULT 'standard',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    prefix TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT 'read,write',
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    provider TEXT NOT NULL DEFAULT 'google',
    status TEXT NOT NULL DEFAULT 'active',
    dns_configured INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inboxes (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    domain TEXT NOT NULL,
    warmup_started_at TEXT NOT NULL,
    daily_cap INTEGER NOT NULL DEFAULT 30,
    status TEXT NOT NULL DEFAULT 'warming',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    name TEXT NOT NULL,
    metric TEXT NOT NULL DEFAULT 'positive_reply',
    status TEXT NOT NULL DEFAULT 'running',
    winner TEXT,
    min_sample INTEGER NOT NULL DEFAULT 60,
    alpha REAL NOT NULL DEFAULT 0.05,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS variants (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    key TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    opener_hint TEXT NOT NULL DEFAULT '',
    sent INTEGER NOT NULL DEFAULT 0,
    positives INTEGER NOT NULL DEFAULT 0,
    UNIQUE(experiment_id, key)
);
CREATE TABLE IF NOT EXISTS assignments (
    lead_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    variant_key TEXT NOT NULL,
    assigned_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id TEXT PRIMARY KEY,
    client_id TEXT,
    url TEXT NOT NULL,
    secret TEXT NOT NULL,
    events TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    response_code INTEGER,
    next_attempt_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    sample_size INTEGER NOT NULL DEFAULT 0,
    win_rate REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppressions (
    email TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signal_events (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    detected_at TEXT NOT NULL
);
"""
