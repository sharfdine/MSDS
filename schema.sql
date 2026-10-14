-- =============================================================================
-- PHC MSDS Category I Continuous Quality Monitoring (CQM) PostgreSQL Schema
-- Edition: PHC-MSDS-Cat1-Ed2-2024.2 (30 Standards, 162 Total Indicators, 15 CQM)
-- =============================================================================

CREATE TABLE IF NOT EXISTS msds_editions (
    edition_id VARCHAR(64) PRIMARY KEY,
    authority VARCHAR(128) NOT NULL,
    facility_category VARCHAR(128) NOT NULL,
    config_yaml TEXT NOT NULL,
    version_hash VARCHAR(64) NOT NULL,
    effective_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS indicators (
    indicator_id VARCHAR(16) PRIMARY KEY,
    edition_id VARCHAR(64) NOT NULL REFERENCES msds_editions(edition_id),
    indicator_number INTEGER NOT NULL,
    msds_code VARCHAR(32) NOT NULL,
    standard_no INTEGER NOT NULL,
    standard_name VARCHAR(128) NOT NULL,
    name VARCHAR(256) NOT NULL,
    ingestion_mode VARCHAR(32) NOT NULL CHECK (ingestion_mode IN ('Automatic', 'Imported', 'Manual')),
    hims_source VARCHAR(256) NOT NULL,
    schedule_cron VARCHAR(64) NOT NULL,
    owner_role VARCHAR(128) NOT NULL,
    owner_name VARCHAR(128) NOT NULL,
    rule_type VARCHAR(64) NOT NULL,
    direction VARCHAR(32) NOT NULL,
    rule_config JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS kpi_measurements (
    measurement_id BIGSERIAL PRIMARY KEY,
    indicator_id VARCHAR(16) NOT NULL REFERENCES indicators(indicator_id),
    period_date DATE NOT NULL,
    numerator NUMERIC(14, 2) NOT NULL,
    denominator NUMERIC(14, 2) NOT NULL,
    emergency_numerator NUMERIC(14, 2),
    emergency_denominator NUMERIC(14, 2),
    routine_numerator NUMERIC(14, 2),
    routine_denominator NUMERIC(14, 2),
    computed_value NUMERIC(10, 4) NOT NULL,
    emergency_pct NUMERIC(10, 4),
    routine_pct NUMERIC(10, 4),
    deterministic_status VARCHAR(32) NOT NULL CHECK (deterministic_status IN ('Fully Met', 'Partially Met', 'Not Met', 'Data Gap')),
    rule_trace TEXT NOT NULL,
    ingestion_mode VARCHAR(32) NOT NULL,
    source_batch_id VARCHAR(64) NOT NULL,
    pulled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (indicator_id, period_date)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id VARCHAR(32) PRIMARY KEY,
    indicator_id VARCHAR(16) NOT NULL REFERENCES indicators(indicator_id),
    period_date DATE NOT NULL,
    severity VARCHAR(24) NOT NULL CHECK (severity IN ('Critical', 'High', 'Data gap', 'Medium', 'Watch')),
    severity_rank INTEGER NOT NULL,
    trigger_type VARCHAR(64) NOT NULL,
    title VARCHAR(256) NOT NULL,
    deterministic_reason TEXT NOT NULL,
    owner_role VARCHAR(128) NOT NULL,
    owner_name VARCHAR(128) NOT NULL,
    suggested_action TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'Open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS corrective_actions (
    capa_id VARCHAR(32) PRIMARY KEY,
    alert_id VARCHAR(32) REFERENCES alerts(alert_id),
    indicator_id VARCHAR(16) NOT NULL REFERENCES indicators(indicator_id),
    title VARCHAR(256) NOT NULL,
    root_cause_summary TEXT NOT NULL,
    action_plan TEXT NOT NULL,
    owner_name VARCHAR(128) NOT NULL,
    owner_role VARCHAR(128) NOT NULL,
    due_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('Assigned', 'In Progress', 'Escalated', 'Closed - Verified')),
    escalation_level INTEGER NOT NULL DEFAULT 0,
    reminder_count INTEGER NOT NULL DEFAULT 0,
    closed_at TIMESTAMPTZ,
    closed_by VARCHAR(128),
    verification_evidence TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_narratives (
    narrative_id VARCHAR(32) PRIMARY KEY,
    scope_type VARCHAR(32) NOT NULL CHECK (scope_type IN ('Indicator_Explanation', 'Monthly_CQI_Report', 'CAPA_Proposal')),
    indicator_id VARCHAR(16),
    report_month VARCHAR(16),
    prompt_hash VARCHAR(64) NOT NULL,
    phi_scrubbed BOOLEAN NOT NULL DEFAULT TRUE,
    source_citations JSONB NOT NULL,
    draft_text TEXT NOT NULL,
    confirmation_status VARCHAR(32) NOT NULL DEFAULT 'Pending Human Confirmation'
        CHECK (confirmation_status IN ('Pending Human Confirmation', 'Confirmed', 'Edited & Confirmed', 'Rejected')),
    confirmed_by VARCHAR(128),
    confirmed_role VARCHAR(64),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_trail (
    audit_id BIGSERIAL PRIMARY KEY,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_name VARCHAR(128) NOT NULL,
    actor_role VARCHAR(64) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    target_entity VARCHAR(64) NOT NULL,
    details TEXT NOT NULL,
    ip_or_session VARCHAR(64) NOT NULL DEFAULT 'HIMS-Internal-VLAN'
);

CREATE INDEX IF NOT EXISTS idx_kpi_ind_date ON kpi_measurements(indicator_id, period_date DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity_rank ASC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_capa_status ON corrective_actions(status, due_date);