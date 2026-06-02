-- ticket_meta schema — BILL-51
-- One row per ticket; indexed for fast equality/range filtering.
-- Picked up automatically by init-schema.sh (lex-sorted *.sql glob).

CREATE TABLE IF NOT EXISTS ticket_meta (
    source             TEXT NOT NULL,
    ticket_id          TEXT NOT NULL,
    project            TEXT,
    state_norm         TEXT,        -- 'open' | 'in_progress' | 'done' | 'canceled'
    state_name         TEXT,        -- raw label from system: "In Progress" etc.
    assignee           TEXT,        -- primary assignee name/login
    reporter           TEXT,
    priority_num       INT,         -- 0=none 1=urgent 2=high 3=medium 4=low
    priority_name      TEXT,        -- "High", "Urgent" etc.
    issue_type         TEXT,        -- 'bug'|'feature'|'task'|'epic' or raw
    labels             TEXT[],      -- all labels/tags
    milestone          TEXT,
    ticket_created_at  TIMESTAMPTZ,
    ticket_updated_at  TIMESTAMPTZ,
    ticket_closed_at   TIMESTAMPTZ,
    title              TEXT,
    PRIMARY KEY (source, ticket_id)
);

CREATE INDEX IF NOT EXISTS ticket_meta_assignee_idx      ON ticket_meta (assignee);
CREATE INDEX IF NOT EXISTS ticket_meta_state_norm_idx    ON ticket_meta (state_norm);
CREATE INDEX IF NOT EXISTS ticket_meta_priority_num_idx  ON ticket_meta (priority_num);
CREATE INDEX IF NOT EXISTS ticket_meta_labels_idx        ON ticket_meta USING gin (labels);
CREATE INDEX IF NOT EXISTS ticket_meta_created_at_idx    ON ticket_meta (ticket_created_at);
CREATE INDEX IF NOT EXISTS ticket_meta_updated_at_idx    ON ticket_meta (ticket_updated_at);
CREATE INDEX IF NOT EXISTS ticket_meta_project_state_idx ON ticket_meta (project, state_norm);
