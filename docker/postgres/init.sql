-- Initial PostgreSQL schema placeholder for Exness Trading Bot
-- Full schema will be implemented in Phase 6 with SQLAlchemy + Alembic

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Placeholder: audit that init script ran
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(32) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_version (version) VALUES ('0.1.0-foundation');
