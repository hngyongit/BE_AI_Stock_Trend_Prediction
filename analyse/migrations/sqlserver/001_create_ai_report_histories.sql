CREATE TABLE ai_report_histories (
    id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),

    report_id NVARCHAR(120) NOT NULL UNIQUE,

    mongo_user_id NVARCHAR(64) NOT NULL,
    user_email NVARCHAR(255) NULL,

    mongo_watchlist_id NVARCHAR(64) NULL,
    mongo_stock_id NVARCHAR(64) NULL,

    symbol NVARCHAR(20) NOT NULL,
    exchange NVARCHAR(20) NOT NULL,
    company NVARCHAR(255) NULL,

    provider NVARCHAR(50) NOT NULL,
    model NVARCHAR(100) NOT NULL,

    risk_profile NVARCHAR(30) NULL,
    time_horizon NVARCHAR(30) NULL,
    include_external_research BIT NOT NULL DEFAULT 1,

    total_score DECIMAL(6,2) NULL,
    risk_score DECIMAL(6,2) NULL,
    data_confidence DECIMAL(6,2) NULL,
    decision_label NVARCHAR(120) NULL,

    report_json NVARCHAR(MAX) NOT NULL,
    summary_snapshot NVARCHAR(MAX) NULL,

    source_hash NVARCHAR(128) NULL,
    request_hash NVARCHAR(128) NULL,

    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE INDEX IX_ai_report_histories_user_created
ON ai_report_histories (mongo_user_id, created_at DESC);

CREATE INDEX IX_ai_report_histories_user_symbol_created
ON ai_report_histories (mongo_user_id, symbol, exchange, created_at DESC);

CREATE INDEX IX_ai_report_histories_report_id
ON ai_report_histories (report_id);

-- Optional for SQL Server 2016+:
-- ALTER TABLE ai_report_histories
-- ADD CONSTRAINT CK_ai_report_histories_report_json_is_json
-- CHECK (ISJSON(report_json) = 1);
