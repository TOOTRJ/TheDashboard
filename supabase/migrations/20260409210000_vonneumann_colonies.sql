-- Colony metadata table for tracking strategy, config, and status per colony.
-- vn_colonies.id serves as the run_id across vn_probes, vn_trades,
-- vn_fitness_snapshots, and vn_generation_stats.

CREATE TABLE vn_colonies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    strategy TEXT NOT NULL DEFAULT 'genetic_algorithm',
    config JSONB NOT NULL DEFAULT '{}',
    mode TEXT NOT NULL DEFAULT 'simulation',
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_vn_colonies_user_id ON vn_colonies(user_id);
CREATE INDEX idx_vn_colonies_status ON vn_colonies(status);

ALTER TABLE vn_colonies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own colonies"
    ON vn_colonies FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own colonies"
    ON vn_colonies FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own colonies"
    ON vn_colonies FOR UPDATE
    USING (auth.uid() = user_id);

-- Auto-update updated_at
CREATE TRIGGER set_vn_colonies_updated_at
    BEFORE UPDATE ON vn_colonies
    FOR EACH ROW
    EXECUTE FUNCTION moddatetime(updated_at);
