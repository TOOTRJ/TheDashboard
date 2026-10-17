-- Independent declaration. Each named section is one fresh-table constructor.
-- Only the emitter may compose these fixed sections; this is not a migration.
-- BEGIN market_sentiment
CREATE TABLE public.market_sentiment (
    id pg_catalog.uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    score pg_catalog.int4 NOT NULL,
    sentiment pg_catalog.text NOT NULL,
    summary pg_catalog.text NOT NULL,
    key_factors pg_catalog.jsonb NOT NULL DEFAULT '[]'::pg_catalog.jsonb,
    date pg_catalog.date NOT NULL DEFAULT CURRENT_DATE,
    source pg_catalog.text DEFAULT 'grok'::pg_catalog.text,
    created_at pg_catalog.timestamptz DEFAULT pg_catalog.now(),
    CONSTRAINT market_sentiment_pkey PRIMARY KEY (id),
    CONSTRAINT market_sentiment_date_key UNIQUE (date),
    CONSTRAINT market_sentiment_score_check CHECK (score >= 0 AND score <= 100),
    CONSTRAINT market_sentiment_sentiment_check CHECK
        (sentiment = ANY (ARRAY['bullish'::pg_catalog.text, 'bearish'::pg_catalog.text, 'neutral'::pg_catalog.text]))
) USING heap;
CREATE INDEX idx_market_sentiment_date ON public.market_sentiment USING btree (date DESC);
ALTER TABLE public.market_sentiment ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.market_sentiment FROM anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE public.market_sentiment TO service_role;
-- END market_sentiment
-- BEGIN test_events
CREATE TABLE public.test_events (
    id pg_catalog.uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    payload pg_catalog.jsonb NOT NULL,
    source pg_catalog.text DEFAULT 'unknown'::pg_catalog.text,
    created_at pg_catalog.timestamptz DEFAULT pg_catalog.now(),
    CONSTRAINT test_events_pkey PRIMARY KEY (id)
) USING heap;
CREATE INDEX idx_test_events_created_at ON public.test_events USING btree (created_at DESC);
ALTER TABLE public.test_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.test_events FROM anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE public.test_events TO service_role;
-- END test_events
