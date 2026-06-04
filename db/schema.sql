--
-- PostgreSQL database dump
--

\restrict xfARZwgA4sBVRGcBWQjBPe6dWOiFo7xXgQBGwZHd22usUppZ8SFQaSClHMapDBf

-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3 (Ubuntu 18.3-1.pgdg24.04+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: _tenants_set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public._tenants_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


--
-- Name: _user_credentials_set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public._user_credentials_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


--
-- Name: borsenhirn_disable_rls(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.borsenhirn_disable_rls(target_table text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', target_table);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', target_table);
    RAISE NOTICE 'RLS deshabilitado en % (Â¡cuidado!)', target_table;
END;
$$;


--
-- Name: borsenhirn_enable_rls(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.borsenhirn_enable_rls(target_table text) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    has_column boolean;
    policy_name text := 'tenant_isolation';
BEGIN
    -- 1. Â¿Existe ya la columna tenant_id?
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = target_table
           AND column_name = 'tenant_id'
    ) INTO has_column;

    IF NOT has_column THEN
        EXECUTE format('ALTER TABLE %I ADD COLUMN tenant_id uuid', target_table);
        EXECUTE format(
            'UPDATE %I SET tenant_id = %L WHERE tenant_id IS NULL',
            target_table, '00000000-0000-0000-0000-000000000000'
        );
        EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id SET NOT NULL',
                       target_table);
        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I_tenant_fk
             FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
             ON DELETE RESTRICT',
            target_table, target_table
        );
        EXECUTE format(
            'CREATE INDEX %I ON %I(tenant_id)',
            'idx_' || target_table || '_tenant', target_table
        );
    END IF;

    -- 2. Habilitar RLS + FORCE RLS
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', target_table);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', target_table);

    -- 3. Crear policy si no existe
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE tablename = target_table AND policyname = policy_name
    ) THEN
        EXECUTE format(
            'CREATE POLICY %I ON %I
                 FOR ALL
                 USING (tenant_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid)
                 WITH CHECK (tenant_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid)',
            policy_name, target_table
        );
    END IF;

    RAISE NOTICE 'RLS habilitado en %', target_table;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alerts_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts_log (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    level text NOT NULL,
    subject text NOT NULL,
    body text,
    meta jsonb DEFAULT '{}'::jsonb,
    acknowledged boolean DEFAULT false NOT NULL,
    ack_at timestamp with time zone,
    ack_note text,
    tenant_id uuid NOT NULL,
    CONSTRAINT alerts_log_level_check CHECK ((level = ANY (ARRAY['INFO'::text, 'WARN'::text, 'CRITICAL'::text])))
);

ALTER TABLE ONLY public.alerts_log FORCE ROW LEVEL SECURITY;


--
-- Name: alerts_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alerts_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alerts_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alerts_log_id_seq OWNED BY public.alerts_log.id;


--
-- Name: assistant_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assistant_history (
    id integer NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.assistant_history FORCE ROW LEVEL SECURITY;


--
-- Name: assistant_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.assistant_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: assistant_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.assistant_history_id_seq OWNED BY public.assistant_history.id;


--
-- Name: assistant_suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assistant_suggestions (
    id integer NOT NULL,
    suggestion text NOT NULL,
    context text,
    applied boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.assistant_suggestions FORCE ROW LEVEL SECURITY;


--
-- Name: assistant_suggestions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.assistant_suggestions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: assistant_suggestions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.assistant_suggestions_id_seq OWNED BY public.assistant_suggestions.id;


--
-- Name: bot_daily_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_daily_state (
    id integer NOT NULL,
    state_date date NOT NULL,
    trades_today integer DEFAULT 0 NOT NULL,
    wins_today integer DEFAULT 0 NOT NULL,
    losses_today integer DEFAULT 0 NOT NULL,
    day_start_equity numeric(18,4),
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_daily_state FORCE ROW LEVEL SECURITY;


--
-- Name: bot_daily_state_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bot_daily_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bot_daily_state_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bot_daily_state_id_seq OWNED BY public.bot_daily_state.id;


--
-- Name: bot_entry_context; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_entry_context (
    symbol character varying(16) NOT NULL,
    rsi numeric(8,2),
    regime character varying(16),
    vix numeric(8,2),
    ma_trend character varying(16),
    ml_prob numeric(8,4),
    entry_price numeric(18,4),
    highest_price numeric(18,4),
    entry_date date,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_entry_context FORCE ROW LEVEL SECURITY;


--
-- Name: bot_entry_prices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_entry_prices (
    symbol character varying(16) NOT NULL,
    state_date date NOT NULL,
    entry_price numeric(18,4) NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_entry_prices FORCE ROW LEVEL SECURITY;


--
-- Name: bot_ml_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_ml_metrics (
    id integer NOT NULL,
    trained_date date NOT NULL,
    accuracy numeric(8,4),
    precision_score numeric(8,4),
    recall_score numeric(8,4),
    f1_score numeric(8,4),
    n_samples integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_ml_metrics FORCE ROW LEVEL SECURITY;


--
-- Name: bot_ml_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bot_ml_metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bot_ml_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bot_ml_metrics_id_seq OWNED BY public.bot_ml_metrics.id;


--
-- Name: bot_ml_training; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_ml_training (
    id integer NOT NULL,
    trained_date date NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_ml_training FORCE ROW LEVEL SECURITY;


--
-- Name: bot_ml_training_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bot_ml_training_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bot_ml_training_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bot_ml_training_id_seq OWNED BY public.bot_ml_training.id;


--
-- Name: bot_performance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_performance (
    perf_date date NOT NULL,
    equity numeric(18,4) NOT NULL,
    pnl numeric(18,4) NOT NULL,
    trades integer DEFAULT 0 NOT NULL,
    wins integer DEFAULT 0 NOT NULL,
    losses integer DEFAULT 0 NOT NULL,
    win_rate numeric(6,4),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_performance FORCE ROW LEVEL SECURITY;


--
-- Name: bot_regime_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_regime_stats (
    regime character varying(16) NOT NULL,
    wins integer DEFAULT 0 NOT NULL,
    losses integer DEFAULT 0 NOT NULL,
    total_pnl numeric(18,4) DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_regime_stats FORCE ROW LEVEL SECURITY;


--
-- Name: bot_symbol_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_symbol_scores (
    symbol character varying(16) NOT NULL,
    score numeric(8,4) DEFAULT 0.5 NOT NULL,
    wins integer DEFAULT 0 NOT NULL,
    losses integer DEFAULT 0 NOT NULL,
    total_pnl numeric(18,4) DEFAULT 0 NOT NULL,
    last_updated date,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_symbol_scores FORCE ROW LEVEL SECURITY;


--
-- Name: bot_trade_outcomes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bot_trade_outcomes (
    id integer NOT NULL,
    trade_date date NOT NULL,
    symbol character varying(16) NOT NULL,
    buy_price numeric(18,4) NOT NULL,
    sell_price numeric(18,4) NOT NULL,
    qty integer NOT NULL,
    pnl numeric(18,4) NOT NULL,
    win boolean NOT NULL,
    reason_sell text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.bot_trade_outcomes FORCE ROW LEVEL SECURITY;


--
-- Name: bot_trade_outcomes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bot_trade_outcomes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bot_trade_outcomes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bot_trade_outcomes_id_seq OWNED BY public.bot_trade_outcomes.id;


--
-- Name: current_tenant_info; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.current_tenant_info AS
 SELECT (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid AS tenant_id,
    CURRENT_USER AS db_user,
    SESSION_USER AS "session_user",
    pg_backend_pid() AS pid;


--
-- Name: daily_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_reports (
    id integer NOT NULL,
    date character varying(10),
    report_type character varying(20),
    content text,
    metrics json,
    created_at timestamp without time zone,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.daily_reports FORCE ROW LEVEL SECURITY;


--
-- Name: daily_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.daily_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: daily_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.daily_reports_id_seq OWNED BY public.daily_reports.id;


--
-- Name: killswitch_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.killswitch_state (
    key text NOT NULL,
    triggered boolean DEFAULT false NOT NULL,
    reason text,
    data jsonb DEFAULT '{}'::jsonb,
    triggered_at timestamp with time zone,
    cleared_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.killswitch_state FORCE ROW LEVEL SECURITY;


--
-- Name: signals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signals (
    id integer NOT NULL,
    "timestamp" timestamp without time zone,
    symbol character varying(10),
    source character varying(20),
    signal_type character varying(20),
    score double precision,
    extra_data json,
    consumed boolean,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.signals FORCE ROW LEVEL SECURITY;


--
-- Name: signals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.signals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: signals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.signals_id_seq OWNED BY public.signals.id;


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    tenant_id uuid NOT NULL,
    slug text NOT NULL,
    email text NOT NULL,
    display_name text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    suspended_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT tenants_status_check CHECK ((status = ANY (ARRAY['active'::text, 'suspended'::text, 'disabled'::text, 'deleted'::text])))
);


--
-- Name: trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trades (
    id integer NOT NULL,
    "timestamp" timestamp without time zone,
    symbol character varying(10),
    action character varying(10),
    price double precision,
    qty integer,
    value double precision,
    pnl double precision,
    reason text,
    regime character varying(20),
    vix double precision,
    ml_prob double precision,
    rsi double precision,
    ma_trend character varying(20),
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.trades FORCE ROW LEVEL SECURITY;


--
-- Name: trades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trades_id_seq OWNED BY public.trades.id;


--
-- Name: user_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_credentials (
    user_id uuid NOT NULL,
    provider text NOT NULL,
    api_key_ciphertext bytea NOT NULL,
    api_secret_ciphertext bytea NOT NULL,
    encryption_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    rotated_at timestamp with time zone,
    tenant_id uuid NOT NULL,
    CONSTRAINT user_credentials_api_key_ciphertext_check CHECK ((length(api_key_ciphertext) > 0)),
    CONSTRAINT user_credentials_api_secret_ciphertext_check CHECK ((length(api_secret_ciphertext) > 0)),
    CONSTRAINT user_credentials_encryption_version_check CHECK ((encryption_version >= 1))
);

ALTER TABLE ONLY public.user_credentials FORCE ROW LEVEL SECURITY;


--
-- Name: alerts_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts_log ALTER COLUMN id SET DEFAULT nextval('public.alerts_log_id_seq'::regclass);


--
-- Name: assistant_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assistant_history ALTER COLUMN id SET DEFAULT nextval('public.assistant_history_id_seq'::regclass);


--
-- Name: assistant_suggestions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assistant_suggestions ALTER COLUMN id SET DEFAULT nextval('public.assistant_suggestions_id_seq'::regclass);


--
-- Name: bot_daily_state id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_daily_state ALTER COLUMN id SET DEFAULT nextval('public.bot_daily_state_id_seq'::regclass);


--
-- Name: bot_ml_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_ml_metrics ALTER COLUMN id SET DEFAULT nextval('public.bot_ml_metrics_id_seq'::regclass);


--
-- Name: bot_ml_training id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_ml_training ALTER COLUMN id SET DEFAULT nextval('public.bot_ml_training_id_seq'::regclass);


--
-- Name: bot_trade_outcomes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_trade_outcomes ALTER COLUMN id SET DEFAULT nextval('public.bot_trade_outcomes_id_seq'::regclass);


--
-- Name: daily_reports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_reports ALTER COLUMN id SET DEFAULT nextval('public.daily_reports_id_seq'::regclass);


--
-- Name: signals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signals ALTER COLUMN id SET DEFAULT nextval('public.signals_id_seq'::regclass);


--
-- Name: trades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades ALTER COLUMN id SET DEFAULT nextval('public.trades_id_seq'::regclass);


--
-- Name: alerts_log alerts_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts_log
    ADD CONSTRAINT alerts_log_pkey PRIMARY KEY (id);


--
-- Name: assistant_history assistant_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assistant_history
    ADD CONSTRAINT assistant_history_pkey PRIMARY KEY (id);


--
-- Name: assistant_suggestions assistant_suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assistant_suggestions
    ADD CONSTRAINT assistant_suggestions_pkey PRIMARY KEY (id);


--
-- Name: bot_daily_state bot_daily_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_daily_state
    ADD CONSTRAINT bot_daily_state_pkey PRIMARY KEY (id);


--
-- Name: bot_daily_state bot_daily_state_state_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_daily_state
    ADD CONSTRAINT bot_daily_state_state_date_key UNIQUE (state_date);


--
-- Name: bot_entry_context bot_entry_context_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_entry_context
    ADD CONSTRAINT bot_entry_context_pkey PRIMARY KEY (symbol);


--
-- Name: bot_entry_prices bot_entry_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_entry_prices
    ADD CONSTRAINT bot_entry_prices_pkey PRIMARY KEY (symbol, state_date);


--
-- Name: bot_ml_metrics bot_ml_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_ml_metrics
    ADD CONSTRAINT bot_ml_metrics_pkey PRIMARY KEY (id);


--
-- Name: bot_ml_training bot_ml_training_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_ml_training
    ADD CONSTRAINT bot_ml_training_pkey PRIMARY KEY (id);


--
-- Name: bot_performance bot_performance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_performance
    ADD CONSTRAINT bot_performance_pkey PRIMARY KEY (perf_date);


--
-- Name: bot_regime_stats bot_regime_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_regime_stats
    ADD CONSTRAINT bot_regime_stats_pkey PRIMARY KEY (regime);


--
-- Name: bot_symbol_scores bot_symbol_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_symbol_scores
    ADD CONSTRAINT bot_symbol_scores_pkey PRIMARY KEY (symbol);


--
-- Name: bot_trade_outcomes bot_trade_outcomes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_trade_outcomes
    ADD CONSTRAINT bot_trade_outcomes_pkey PRIMARY KEY (id);


--
-- Name: daily_reports daily_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_reports
    ADD CONSTRAINT daily_reports_pkey PRIMARY KEY (id);


--
-- Name: killswitch_state killswitch_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.killswitch_state
    ADD CONSTRAINT killswitch_state_pkey PRIMARY KEY (key);


--
-- Name: signals signals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signals
    ADD CONSTRAINT signals_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (tenant_id);


--
-- Name: tenants tenants_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_slug_key UNIQUE (slug);


--
-- Name: trades trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (id);


--
-- Name: user_credentials user_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_credentials
    ADD CONSTRAINT user_credentials_pkey PRIMARY KEY (user_id, provider);


--
-- Name: idx_alerts_level_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_level_time ON public.alerts_log USING btree (level, created_at DESC);


--
-- Name: idx_alerts_unacked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_unacked ON public.alerts_log USING btree (created_at DESC) WHERE (acknowledged = false);


--
-- Name: idx_killswitch_triggered; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_killswitch_triggered ON public.killswitch_state USING btree (triggered) WHERE (triggered = true);


--
-- Name: idx_tenants_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenants_email ON public.tenants USING btree (lower(email));


--
-- Name: idx_tenants_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenants_status ON public.tenants USING btree (status) WHERE (status = 'active'::text);


--
-- Name: idx_user_credentials_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_credentials_user ON public.user_credentials USING btree (user_id);


--
-- Name: idx_user_credentials_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_credentials_version ON public.user_credentials USING btree (encryption_version) WHERE (encryption_version > 1);


--
-- Name: ix_alerts_log_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_log_tenant_id ON public.alerts_log USING btree (tenant_id);


--
-- Name: ix_assistant_history_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assistant_history_tenant_id ON public.assistant_history USING btree (tenant_id);


--
-- Name: ix_assistant_suggestions_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assistant_suggestions_tenant_id ON public.assistant_suggestions USING btree (tenant_id);


--
-- Name: ix_bot_daily_state_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_daily_state_tenant_id ON public.bot_daily_state USING btree (tenant_id);


--
-- Name: ix_bot_entry_context_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_entry_context_tenant_id ON public.bot_entry_context USING btree (tenant_id);


--
-- Name: ix_bot_entry_prices_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_entry_prices_tenant_id ON public.bot_entry_prices USING btree (tenant_id);


--
-- Name: ix_bot_ml_metrics_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_ml_metrics_tenant_id ON public.bot_ml_metrics USING btree (tenant_id);


--
-- Name: ix_bot_ml_training_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_ml_training_tenant_id ON public.bot_ml_training USING btree (tenant_id);


--
-- Name: ix_bot_performance_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_performance_tenant_id ON public.bot_performance USING btree (tenant_id);


--
-- Name: ix_bot_regime_stats_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_regime_stats_tenant_id ON public.bot_regime_stats USING btree (tenant_id);


--
-- Name: ix_bot_symbol_scores_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_symbol_scores_tenant_id ON public.bot_symbol_scores USING btree (tenant_id);


--
-- Name: ix_bot_trade_outcomes_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bot_trade_outcomes_tenant_id ON public.bot_trade_outcomes USING btree (tenant_id);


--
-- Name: ix_daily_reports_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_reports_date ON public.daily_reports USING btree (date);


--
-- Name: ix_daily_reports_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_reports_tenant_id ON public.daily_reports USING btree (tenant_id);


--
-- Name: ix_killswitch_state_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_killswitch_state_tenant_id ON public.killswitch_state USING btree (tenant_id);


--
-- Name: ix_signals_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signals_symbol ON public.signals USING btree (symbol);


--
-- Name: ix_signals_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signals_tenant_id ON public.signals USING btree (tenant_id);


--
-- Name: ix_signals_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signals_timestamp ON public.signals USING btree ("timestamp");


--
-- Name: ix_trades_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trades_symbol ON public.trades USING btree (symbol);


--
-- Name: ix_trades_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trades_tenant_id ON public.trades USING btree (tenant_id);


--
-- Name: ix_trades_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trades_timestamp ON public.trades USING btree ("timestamp");


--
-- Name: ix_user_credentials_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_credentials_tenant_id ON public.user_credentials USING btree (tenant_id);


--
-- Name: tenants tenants_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER tenants_updated_at BEFORE UPDATE ON public.tenants FOR EACH ROW EXECUTE FUNCTION public._tenants_set_updated_at();


--
-- Name: user_credentials user_credentials_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER user_credentials_updated_at BEFORE UPDATE ON public.user_credentials FOR EACH ROW EXECUTE FUNCTION public._user_credentials_set_updated_at();


--
-- Name: alerts_log fk_alerts_log_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts_log
    ADD CONSTRAINT fk_alerts_log_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: assistant_history fk_assistant_history_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assistant_history
    ADD CONSTRAINT fk_assistant_history_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: assistant_suggestions fk_assistant_suggestions_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assistant_suggestions
    ADD CONSTRAINT fk_assistant_suggestions_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_daily_state fk_bot_daily_state_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_daily_state
    ADD CONSTRAINT fk_bot_daily_state_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_entry_context fk_bot_entry_context_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_entry_context
    ADD CONSTRAINT fk_bot_entry_context_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_entry_prices fk_bot_entry_prices_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_entry_prices
    ADD CONSTRAINT fk_bot_entry_prices_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_ml_metrics fk_bot_ml_metrics_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_ml_metrics
    ADD CONSTRAINT fk_bot_ml_metrics_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_ml_training fk_bot_ml_training_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_ml_training
    ADD CONSTRAINT fk_bot_ml_training_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_performance fk_bot_performance_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_performance
    ADD CONSTRAINT fk_bot_performance_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_regime_stats fk_bot_regime_stats_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_regime_stats
    ADD CONSTRAINT fk_bot_regime_stats_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_symbol_scores fk_bot_symbol_scores_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_symbol_scores
    ADD CONSTRAINT fk_bot_symbol_scores_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: bot_trade_outcomes fk_bot_trade_outcomes_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bot_trade_outcomes
    ADD CONSTRAINT fk_bot_trade_outcomes_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: daily_reports fk_daily_reports_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_reports
    ADD CONSTRAINT fk_daily_reports_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: killswitch_state fk_killswitch_state_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.killswitch_state
    ADD CONSTRAINT fk_killswitch_state_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: signals fk_signals_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signals
    ADD CONSTRAINT fk_signals_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: trades fk_trades_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT fk_trades_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: user_credentials fk_user_credentials_tenant; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_credentials
    ADD CONSTRAINT fk_user_credentials_tenant FOREIGN KEY (tenant_id) REFERENCES public.tenants(tenant_id) ON DELETE RESTRICT;


--
-- Name: alerts_log admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.alerts_log USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: assistant_history admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.assistant_history USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: assistant_suggestions admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.assistant_suggestions USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_daily_state admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_daily_state USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_entry_context admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_entry_context USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_entry_prices admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_entry_prices USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_ml_metrics admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_ml_metrics USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_ml_training admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_ml_training USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_performance admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_performance USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_regime_stats admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_regime_stats USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_symbol_scores admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_symbol_scores USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: bot_trade_outcomes admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.bot_trade_outcomes USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: daily_reports admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.daily_reports USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: killswitch_state admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.killswitch_state USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: signals admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.signals USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: trades admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.trades USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: user_credentials admin_bypass; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_bypass ON public.user_credentials USING ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text)) WITH CHECK ((NULLIF(current_setting('app.bypass_rls'::text, true), ''::text) = 'on'::text));


--
-- Name: alerts_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.alerts_log ENABLE ROW LEVEL SECURITY;

--
-- Name: assistant_history; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.assistant_history ENABLE ROW LEVEL SECURITY;

--
-- Name: assistant_suggestions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.assistant_suggestions ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_daily_state; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_daily_state ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_entry_context; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_entry_context ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_entry_prices; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_entry_prices ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_ml_metrics; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_ml_metrics ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_ml_training; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_ml_training ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_performance; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_performance ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_regime_stats; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_regime_stats ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_symbol_scores; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_symbol_scores ENABLE ROW LEVEL SECURITY;

--
-- Name: bot_trade_outcomes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bot_trade_outcomes ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: killswitch_state; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.killswitch_state ENABLE ROW LEVEL SECURITY;

--
-- Name: signals; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.signals ENABLE ROW LEVEL SECURITY;

--
-- Name: alerts_log tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.alerts_log USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: assistant_history tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.assistant_history USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: assistant_suggestions tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.assistant_suggestions USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_daily_state tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_daily_state USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_entry_context tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_entry_context USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_entry_prices tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_entry_prices USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_ml_metrics tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_ml_metrics USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_ml_training tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_ml_training USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_performance tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_performance USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_regime_stats tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_regime_stats USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_symbol_scores tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_symbol_scores USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: bot_trade_outcomes tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.bot_trade_outcomes USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: daily_reports tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.daily_reports USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: killswitch_state tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.killswitch_state USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: signals tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.signals USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: trades tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.trades USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: user_credentials tenant_isolation; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation ON public.user_credentials USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--
-- Name: trades; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;

--
-- Name: user_credentials; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_credentials ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict xfARZwgA4sBVRGcBWQjBPe6dWOiFo7xXgQBGwZHd22usUppZ8SFQaSClHMapDBf

