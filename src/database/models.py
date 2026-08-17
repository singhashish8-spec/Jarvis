"""Database schema definitions (SQL DDL) for the Supabase Postgres
tables Jarvis uses.

These CREATE TABLE statements are the source of truth for schema —
run them once in the Supabase SQL editor (see docs/DATABASE.md), or
via `make verify` / `scripts/setup.sh`, which prints them for you.
"""

TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL, -- running, completed, failed
    input JSONB NOT NULL,
    output JSONB,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    cost DECIMAL(10, 2),
    cost_currency VARCHAR(3) DEFAULT 'INR'
);

CREATE INDEX IF NOT EXISTS idx_tasks_agent_type ON tasks(agent_type);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
"""

PROJECTS_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    owner VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner);
"""

SKILLS_TABLE = """
CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(50) NOT NULL,
    skill_name VARCHAR(255) NOT NULL,
    description TEXT,
    version VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(agent_type, skill_name, version)
);

CREATE INDEX IF NOT EXISTS idx_skills_agent_type ON skills(agent_type);
"""

USAGE_TABLE = """
CREATE TABLE IF NOT EXISTS usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    agent_type VARCHAR(50),
    model_name VARCHAR(100),
    calls_count INTEGER DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    cost DECIMAL(10, 2) DEFAULT 0,
    cost_currency VARCHAR(3) DEFAULT 'INR',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(date, agent_type)
);

CREATE INDEX IF NOT EXISTS idx_usage_date ON usage(date);
CREATE INDEX IF NOT EXISTS idx_usage_agent_type ON usage(agent_type);
"""

ALL_TABLES = [TASKS_TABLE, PROJECTS_TABLE, SKILLS_TABLE, USAGE_TABLE]


def get_init_sql() -> str:
    """Full SQL script to initialize every Jarvis table."""
    return "\n\n".join(ALL_TABLES)
