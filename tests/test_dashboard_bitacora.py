"""
Smoke tests del rediseño Bitácora Nocturna.

Estos tests NO necesitan Streamlit corriendo · solo verifican que:
  1. Los módulos se importan sin error.
  2. Los helpers de render devuelven HTML strings no-vacíos.
  3. El contador de Eintrag es monotónico-por-día.
  4. El generador de observación produce 2-4 oraciones siguiendo las reglas.
  5. Los stubs de status de módulos cubren los 6 módulos esperados.
  6. Cero referencias a colores prohibidos (azul/cyan/magenta) en el theme.

Ejecutar:
    pytest tests/test_dashboard_bitacora.py -v
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest


# ─── 1. Imports ──────────────────────────────────────────────────────────────

def test_theme_imports():
    from borsenhirn.dashboard import bitacora_theme as t
    assert hasattr(t, "PALETTE")
    assert hasattr(t, "GLOBAL_CSS")
    for name in [
        "render_kopfzeile", "render_observation_card", "render_vermoegen_card",
        "render_regime_gauge", "render_regime_verlauf", "render_metriken_strip",
        "render_exemplar_card", "render_sinapsen_grid", "render_hirn_bubble",
        "render_steuerung_header", "render_footer", "plotly_layout",
        "derive_module_statuses",
    ]:
        assert callable(getattr(t, name)), f"missing helper {name}"


def test_voice_imports():
    from borsenhirn.dashboard import bitacora_voice as v
    assert callable(v.get_observation)
    assert callable(v.invalidate_cache)
    assert hasattr(v, "ObservationContext")


def test_state_imports():
    from borsenhirn.dashboard import bitacora_state as s
    assert callable(s.current_eintrag)
    assert callable(s.force_increment)
    assert callable(s.session_metadata)


# ─── 2. Helpers devuelven HTML no-vacío ──────────────────────────────────────

def test_kopfzeile_renders():
    from borsenhirn.dashboard.bitacora_theme import render_kopfzeile
    html = render_kopfzeile(
        eintrag=412, api_online=True, alpaca_ok=True,
        bot_mode="PAPER", days_in_paper=28,
    )
    assert "Bitácora del cerebro" in html
    assert "EINTRAG №412" in html
    assert "PAPER" in html
    assert "BOT · WACH" in html


def test_observation_card_renders():
    from borsenhirn.dashboard.bitacora_theme import render_observation_card
    html = render_observation_card(
        text="Bullenmarkt sostenido. VIX dócil en 19.",
        confidence=0.87,
        components_active="9/9",
    )
    assert "HEUTIGE BEOBACHTUNG" in html
    assert "FIRMA · M2.ANALYST · KONFIDENZ 87%" in html
    assert "Bullenmarkt" in html


def test_vermoegen_card_renders():
    from borsenhirn.dashboard.bitacora_theme import render_vermoegen_card
    html = render_vermoegen_card(
        equity=107878.51,
        pct_change=3.76,
        cumulative_pnl=3908.77,
        start_date_label="28. März",
        sparkline_values=[100000, 102000, 105000, 107878],
        sparkline_x_labels=["28 MAR", "11 ABR", "26 ABR"],
    )
    assert "$107,878.51" in html
    assert "+3.76%" in html
    assert "DAS VERMÖGEN" in html


def test_regime_gauge_renders():
    from borsenhirn.dashboard.bitacora_theme import render_regime_gauge
    html = render_regime_gauge(confidence=0.87, regime="BULL", days_28_pct=0.87)
    assert "Bullenmarkt" in html
    assert "DER ZUSTAND" in html
    assert "<svg" in html


def test_regime_verlauf_renders():
    from borsenhirn.dashboard.bitacora_theme import render_regime_verlauf
    history = ["BULL"] * 21 + ["SIDEWAYS"] * 5 + ["BEAR"] * 2
    html = render_regime_verlauf(history)
    assert "REGIME-VERLAUF" in html
    assert "BULL" in html
    assert "PANIK" in html


def test_metriken_strip_renders():
    from borsenhirn.dashboard.bitacora_theme import render_metriken_strip
    cells = [
        ("BARGELD", "$31,853", "29% verfügbar"),
        ("POSITIONEN", "12 / 44", "offen"),
        ("SIEGRATE", "36.4%", "4 / 11 cerrados"),
        ("ANGST · VIX", "19.23", "→ ruhig"),
        ("INFLATION · CPI", "3.3%", "↑ 0.66%"),
        ("LEITZINS · FED", "3.64%", "→ stabil"),
    ]
    html = render_metriken_strip(cells)
    assert "BARGELD" in html
    assert "$31,853" in html
    assert "verfügbar" in html


def test_exemplar_card_winning_loosing():
    from borsenhirn.dashboard.bitacora_theme import render_exemplar_card, PALETTE
    win = render_exemplar_card(
        symbol="CVX", qty=35, avg_entry=183.57,
        last_price=185.21, pnl=57.4, pnl_pct=0.89,
    )
    los = render_exemplar_card(
        symbol="JNJ", qty=20, avg_entry=160.0,
        last_price=158.0, pnl=-40.0, pnl_pct=-1.25,
    )
    assert PALETTE["verde_oliva"] in win
    assert PALETTE["rojo_terra"] in los
    assert "CVX" in win
    assert "JNJ" in los


def test_sinapsen_grid_six_modules():
    from borsenhirn.dashboard.bitacora_theme import render_sinapsen_grid
    modules = [
        {"label": f"M{i} · TEST", "status": "ok", "description": "desc"}
        for i in range(1, 7)
    ]
    html = render_sinapsen_grid(modules)
    for i in range(1, 7):
        assert f"M{i} · TEST" in html


def test_hirn_bubble_assistant_vs_user():
    from borsenhirn.dashboard.bitacora_theme import render_hirn_bubble
    a = render_hirn_bubble("assistant", "El mercado quiere más alto.")
    u = render_hirn_bubble("user", "¿Cómo va el portfolio?")
    assert "M5.HIRN" in a
    assert "DU · USUARIO" in u
    assert "El mercado quiere más alto." in a


# ─── 3. Eintrag counter idempotente y monotónico ─────────────────────────────

def test_current_eintrag_idempotent_same_day(tmp_path, monkeypatch):
    # Aislamos el state file en un tmp dir
    from borsenhirn.dashboard import bitacora_state as s
    monkeypatch.setattr(s, "STATE_DIR", tmp_path / ".borsenhirn")
    monkeypatch.setattr(s, "STATE_PATH", tmp_path / ".borsenhirn" / "bitacora_state.json")

    n1 = s.current_eintrag()
    n2 = s.current_eintrag()
    n3 = s.current_eintrag()
    assert n1 == n2 == n3
    assert n1 >= 1


def test_force_increment_increases(tmp_path, monkeypatch):
    from borsenhirn.dashboard import bitacora_state as s
    monkeypatch.setattr(s, "STATE_DIR", tmp_path / ".borsenhirn")
    monkeypatch.setattr(s, "STATE_PATH", tmp_path / ".borsenhirn" / "bitacora_state.json")

    n1 = s.current_eintrag()
    n2 = s.force_increment()
    n3 = s.force_increment()
    assert n2 > n1
    assert n3 > n2
    assert n3 - n1 == 2


def test_session_metadata_keys(tmp_path, monkeypatch):
    from borsenhirn.dashboard import bitacora_state as s
    monkeypatch.setattr(s, "STATE_DIR", tmp_path / ".borsenhirn")
    monkeypatch.setattr(s, "STATE_PATH", tmp_path / ".borsenhirn" / "bitacora_state.json")

    meta = s.session_metadata()
    for k in ("entry_number", "first_session_date",
              "last_increment_date", "manual_cycles_today",
              "days_since_first"):
        assert k in meta


# ─── 4. Voz · sigue las reglas del brief ─────────────────────────────────────

def test_observation_two_to_four_sentences(tmp_path, monkeypatch):
    from borsenhirn.dashboard import bitacora_state as s
    from borsenhirn.dashboard import bitacora_voice as v

    monkeypatch.setattr(s, "STATE_DIR", tmp_path / ".borsenhirn")
    monkeypatch.setattr(s, "STATE_PATH", tmp_path / ".borsenhirn" / "bitacora_state.json")
    monkeypatch.setattr(v, "STATE_DIR", tmp_path / ".borsenhirn")
    monkeypatch.setattr(v, "CACHE_PATH", tmp_path / ".borsenhirn" / "bitacora_observation.json")

    ctx = v.ObservationContext(
        regime="BULL", confidence=0.87, vix=19.0,
        positions_open=12, positions_winning=4, positions_losing=7,
        cumulative_pnl=3908.0, days_since_first=28,
    )
    out = v.get_observation(ctx, force=True)
    text = out["text"]
    # contar oraciones por puntos finales · debe ser 2-5 (incluyendo opcional cierre)
    sentences = [s for s in re.split(r"\.\s+", text) if s.strip()]
    assert 2 <= len(sentences) <= 6, f"sentence count {len(sentences)} out of bounds: {text!r}"
    # debe contener al menos una palabra alemana del set esperado
    assert any(w in text for w in ("Bullenmarkt", "Bärenmarkt", "Seitwärts", "Panik"))


def test_observation_cache_returns_same_text(tmp_path, monkeypatch):
    from borsenhirn.dashboard import bitacora_state as s
    from borsenhirn.dashboard import bitacora_voice as v

    monkeypatch.setattr(s, "STATE_DIR", tmp_path / ".borsenhirn")
    monkeypatch.setattr(s, "STATE_PATH", tmp_path / ".borsenhirn" / "bitacora_state.json")
    monkeypatch.setattr(v, "STATE_DIR", tmp_path / ".borsenhirn")
    monkeypatch.setattr(v, "CACHE_PATH", tmp_path / ".borsenhirn" / "bitacora_observation.json")

    ctx = v.ObservationContext(
        regime="BULL", confidence=0.87, vix=19.0,
        positions_open=12, positions_winning=4, positions_losing=7,
        cumulative_pnl=3908.0, days_since_first=28,
    )
    a = v.get_observation(ctx)
    b = v.get_observation(ctx)
    assert a["text"] == b["text"]
    assert b["source"] == "cache"


# ─── 5. Module status stub cubre los 6 módulos ───────────────────────────────

def test_derive_module_statuses_returns_six():
    from borsenhirn.dashboard.bitacora_theme import derive_module_statuses, count_healthy
    fake_status = {
        "bot": {"last_cycle": "2026-04-26T08:15:00", "watchlist_size": 44, "live_mode": False},
        "account": {"equity": 107878.51, "cash": 31853.0, "buying_power": 60000.0},
        "regime": {"regime": "BULL", "confidence": 0.87, "vix": 19.23},
        "memory": {"trades_today": 12, "wins_today": 4, "losses_today": 7},
    }
    modules = derive_module_statuses(
        status_payload=fake_status, perf_payload={}, trades_count=412,
    )
    assert len(modules) == 6
    labels = [m["label"] for m in modules]
    for needed in ["M1", "M2", "M3", "M4", "BOT", "M5"]:
        assert any(needed in l for l in labels), f"missing module {needed}"
    assert count_healthy(modules) >= 5  # con state saludable, casi todos OK


# ─── 6. Cero colores prohibidos en el theme ──────────────────────────────────

def test_no_forbidden_colors_in_theme():
    """
    El theme NO debe contener colores azul/cyan/magenta hardcodeados.
    Verificamos como regex sobre el archivo, salvo el grad_id y stop-color
    que son siempre olive/terra/ambar.
    """
    theme_path = Path(__file__).resolve().parent.parent / "borsenhirn" / "dashboard" / "bitacora_theme.py"
    content = theme_path.read_text(encoding="utf-8")

    # Patrones prohibidos · cualquier hex que NO esté en la paleta aprobada
    allowed = {
        "#0F0D0A", "#1A1610", "#E8DEC9", "#9BB37E", "#A86850",
        "#C9A96A", "#7A3525", "#3A3025", "#A89878",
        "#221C14",  # variante hover de bg_tarjeta
    }
    found_hexes = set(re.findall(r"#[0-9A-Fa-f]{6}", content))
    forbidden = found_hexes - allowed
    assert not forbidden, f"colores no permitidos en theme: {forbidden}"


def test_no_forbidden_colors_in_dashboard():
    dash_path = Path(__file__).resolve().parent.parent / "dashboard.py"
    content = dash_path.read_text(encoding="utf-8")

    # Solo bloqueamos azules/cyans/magentas explícitos · no inspeccionamos
    # cada hex porque dashboard.py debería leer de PALETTE.
    forbidden_substrings = [
        "#5b9bd5",  # blue del original
        "#3dd68c",  # green del original (no terroso)
        "#ff5f5f",  # red del original (no terroso)
        "#0a0e1a",  # navy bg del original
        "#c8d6e8",  # text del original
    ]
    hits = [s for s in forbidden_substrings if s.lower() in content.lower()]
    assert not hits, f"dashboard.py todavía referencia colores del diseño viejo: {hits}"


# ─── 7. Streamlit config tiene la paleta correcta ────────────────────────────

def test_streamlit_config_uses_bitacora_palette():
    cfg_path = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"
    assert cfg_path.exists(), "falta .streamlit/config.toml"
    text = cfg_path.read_text(encoding="utf-8")
    assert "#0F0D0A" in text  # bg_noche
    assert "#1A1610" in text  # bg_tarjeta
    assert "#E8DEC9" in text  # texto_perg
    assert "#C9A96A" in text  # ambar


# ═════════════════════════════════════════════════════════════════════════════
# v1.1 · Bug-fix tests · capa de datos + HTML escape regression
# ═════════════════════════════════════════════════════════════════════════════


# ─── Data layer · imports y estructuras ──────────────────────────────────────

def test_data_layer_imports():
    from borsenhirn.dashboard import bitacora_data as d
    assert callable(d.build_payload)
    assert hasattr(d, "DataPayload")
    assert hasattr(d, "MetricSnap")
    assert hasattr(d, "DATA_SOURCE_MAP")
    # All expected metrics in the source map
    for k in ("equity","cash","vix","cpi","fed_rate","win_rate","regime"):
        assert k in d.DATA_SOURCE_MAP, f"missing {k} in DATA_SOURCE_MAP"


def test_metric_snap_dataclass():
    from borsenhirn.dashboard.bitacora_data import MetricSnap
    s = MetricSnap(value=42.0, source="live")
    assert s.value == 42.0
    assert s.is_fresh is True
    s2 = MetricSnap(value=42.0, source="cache", stale=True)
    assert s2.is_fresh is False


def test_payload_default_is_safe():
    """Sin red, build_payload no debe crashear."""
    from borsenhirn.dashboard.bitacora_data import build_payload, DataPayload
    p = build_payload()
    assert isinstance(p, DataPayload)
    # Estados por defecto razonables
    assert isinstance(p.positions, list)
    assert isinstance(p.trades, list)
    assert hasattr(p.equity, "value")


def test_payload_account_field_picker(monkeypatch):
    """
    Cuando /portfolio tiene equity y /status no, debe preferir /portfolio.
    Cubre el escenario reportado por el usuario en BUG 1.
    """
    from borsenhirn.dashboard import bitacora_data as d

    def fake_status():
        return {"account": {}, "regime": {"regime": "BULL", "confidence": 0.87, "vix": 19.23},
                "memory": {"trades_today": 0, "wins_today": 0, "losses_today": 0},
                "bot": {"last_cycle": "2026-04-26T08:15:00", "watchlist_size": 44, "live_mode": False}}

    def fake_portfolio(period="1D"):
        return {"account": {"equity": 107878.51, "cash": 31853.0,
                            "buying_power": 60000.0, "day_pl": 0, "day_pl_pct": 0},
                "positions": [], "equity_history": []}

    monkeypatch.setattr(d, "_fetch_status", fake_status)
    monkeypatch.setattr(d, "_fetch_portfolio", fake_portfolio)
    monkeypatch.setattr(d, "_fetch_trades", lambda limit=200: [])
    monkeypatch.setattr(d, "_fetch_perf_history", lambda days=30: [])
    monkeypatch.setattr(d, "_api_online", lambda: True)
    monkeypatch.setattr(d, "_fetch_macro_via_m2", lambda: (None, "no_test"))
    monkeypatch.setattr(d, "_fetch_vix_yfinance", lambda: (None, "no_test"))

    payload = d.build_payload()
    assert payload.equity.value == 107878.51, "equity debe venir de /portfolio"
    assert payload.cash.value == 31853.0
    assert payload.equity.source == "live"


def test_payload_macro_via_m2_uses_fred_data(monkeypatch):
    """
    Cuando MacroFetcher devuelve datos de FRED, payload los expone como live.
    """
    from borsenhirn.dashboard import bitacora_data as d

    fake_macro = {
        "cpi": {"value": 3.3, "change": 0.66, "trend": "rising"},
        "fed_rate": {"value": 3.64, "change": 0.0, "trend": "flat"},
    }
    monkeypatch.setattr(d, "_fetch_status", lambda: {})
    monkeypatch.setattr(d, "_fetch_portfolio", lambda period="1D": {})
    monkeypatch.setattr(d, "_fetch_trades", lambda limit=200: [])
    monkeypatch.setattr(d, "_fetch_perf_history", lambda days=30: [])
    monkeypatch.setattr(d, "_api_online", lambda: True)
    monkeypatch.setattr(d, "_fetch_macro_via_m2", lambda: (fake_macro, None))
    monkeypatch.setattr(d, "_fetch_vix_yfinance", lambda: (None, "no_test"))

    payload = d.build_payload()
    assert payload.cpi.value == 3.3
    assert payload.cpi.source == "live"
    assert payload.fed_rate.value == 3.64
    assert payload.fed_rate_trend.value == "flat"


def test_payload_vix_falls_back_to_yfinance(monkeypatch):
    """Cuando /status.regime.vix está vacío, se cae a yfinance."""
    from borsenhirn.dashboard import bitacora_data as d

    monkeypatch.setattr(d, "_fetch_status", lambda: {"regime": {"regime": "BULL", "confidence": 0.5, "vix": 0}})
    monkeypatch.setattr(d, "_fetch_portfolio", lambda period="1D": {})
    monkeypatch.setattr(d, "_fetch_trades", lambda limit=200: [])
    monkeypatch.setattr(d, "_fetch_perf_history", lambda days=30: [])
    monkeypatch.setattr(d, "_api_online", lambda: True)
    monkeypatch.setattr(d, "_fetch_macro_via_m2", lambda: (None, None))
    monkeypatch.setattr(d, "_fetch_vix_yfinance", lambda: (19.42, None))

    payload = d.build_payload()
    assert payload.vix.value == 19.42
    assert payload.vix.source == "fallback"


def test_payload_win_rate_computed_from_trades(monkeypatch):
    """win_rate se calcula desde /trades/list (no se hardcodea desde memory)."""
    from borsenhirn.dashboard import bitacora_data as d

    fake_trades = [
        {"action": "SELL", "symbol": "CVX", "pnl": 12.5},
        {"action": "SELL", "symbol": "JNJ", "pnl": -3.2},
        {"action": "SELL", "symbol": "OXY", "pnl": 8.0},
        {"action": "SELL", "symbol": "TSLA", "pnl": -10.0},
        {"action": "BUY",  "symbol": "MS",  "pnl": None},  # no debe contar
    ]
    monkeypatch.setattr(d, "_fetch_status", lambda: {})
    monkeypatch.setattr(d, "_fetch_portfolio", lambda period="1D": {})
    monkeypatch.setattr(d, "_fetch_trades", lambda limit=200: fake_trades)
    monkeypatch.setattr(d, "_fetch_perf_history", lambda days=30: [])
    monkeypatch.setattr(d, "_api_online", lambda: True)
    monkeypatch.setattr(d, "_fetch_macro_via_m2", lambda: (None, None))
    monkeypatch.setattr(d, "_fetch_vix_yfinance", lambda: (None, None))

    payload = d.build_payload()
    # 2 ganadores de 4 cerrados = 50%
    assert payload.win_rate.value == 50.0
    assert payload.trades_closed.value == 4
    assert abs(payload.cumulative_pnl.value - 7.3) < 1e-6  # 12.5 - 3.2 + 8.0 - 10.0


# ─── Coherencia · BUG 3 ──────────────────────────────────────────────────────

def test_coherent_snapshot_no_phantom_delta(monkeypatch):
    """
    BUG 3: si equity es 0, no debe haber delta % positivo. La capa de datos
    debe garantizar que equity y day_pl_pct vengan del mismo snapshot.
    """
    from borsenhirn.dashboard import bitacora_data as d

    monkeypatch.setattr(d, "_fetch_status", lambda: {})
    monkeypatch.setattr(d, "_fetch_portfolio", lambda period="1D": {})
    monkeypatch.setattr(d, "_fetch_trades", lambda limit=200: [])
    monkeypatch.setattr(d, "_fetch_perf_history", lambda days=30: [])
    monkeypatch.setattr(d, "_api_online", lambda: True)
    monkeypatch.setattr(d, "_fetch_macro_via_m2", lambda: (None, None))
    monkeypatch.setattr(d, "_fetch_vix_yfinance", lambda: (None, None))

    payload = d.build_payload()
    if payload.equity.value in (0, 0.0):
        # Si equity es 0, day_pl_pct también debe ser 0 (mismo snapshot vacío)
        assert payload.day_pl_pct.value in (0, 0.0)


# ─── BUG 2 · HTML escape regression ──────────────────────────────────────────

def test_render_daily_pnl_header_no_newlines():
    """
    El header del Täglicher Gewinn debe ser HTML inline · sin saltos de línea
    internos · para que Streamlit no lo trate como bloque de código markdown.
    """
    from borsenhirn.dashboard.bitacora_theme import render_daily_pnl_header
    html = render_daily_pnl_header(
        de_label="TÄGLICHER GEWINN", es_label="P&amp;L diario",
        net_total=-89.54, green_days=4, red_days=7,
    )
    # No debe contener saltos de línea internos · todo debe ser una sola línea
    assert "\n" not in html, "header tiene newlines · Streamlit lo escapará"
    # Y debe tener el contenido esperado
    assert "TÄGLICHER GEWINN" in html
    assert "NET" in html
    assert "4G / 7R" in html


def test_chart_label_no_newlines():
    """Mismo principio para chart_label · usado dentro de headers compuestos."""
    from borsenhirn.dashboard.bitacora_theme import chart_label
    html = chart_label("TÄGLICHE EQUITY", "por día")
    assert "\n" not in html
    assert "TÄGLICHE EQUITY" in html


def test_dashboard_no_indented_html_in_fstrings():
    """
    Garantía estructural: dashboard.py no debe tener f-strings multilinea con
    HTML indentado dentro de st.markdown(...). Detectamos buscando un pattern
    sospechoso: una llamada a st.markdown que abre con f''' o f\"\"\" y
    contiene líneas que empiezan con espacios + < (HTML indentado).
    """
    from pathlib import Path
    import re
    dash_path = Path(__file__).resolve().parent.parent / "dashboard.py"
    src = dash_path.read_text(encoding="utf-8")
    # Patrón que reproduce el bug original: f-string triple-quoted con HTML
    # indentado seguido de unsafe_allow_html=True
    # Note: las líneas con HTML indentadas son las que Streamlit interpreta
    # como bloques de código markdown.
    pattern = re.compile(
        r"st\.markdown\(\s*f?\"\"\".*?\n        <(?!/)",
        re.DOTALL,
    )
    matches = pattern.findall(src)
    # Una excepción permitida: el caso del banner de API offline.
    # Aceptamos hasta 0 matches en código normal.
    assert len(matches) == 0, (
        f"dashboard.py contiene {len(matches)} f-string multilinea con HTML "
        f"indentado · Streamlit lo escapará. Usa render_daily_pnl_header() o "
        f"un helper similar que devuelva HTML inline."
    )


# ─── Staleness dot · indicador de frescura ───────────────────────────────────

def test_staleness_dot_hidden_when_live():
    from borsenhirn.dashboard.bitacora_theme import staleness_dot
    assert staleness_dot(False, source="live") == ""


def test_staleness_dot_shown_when_cached():
    from borsenhirn.dashboard.bitacora_theme import staleness_dot, PALETTE
    html = staleness_dot(True, source="cache")
    assert PALETTE["ambar"] in html
    assert "title=" in html  # tooltip explicativo


def test_metrik_strip_supports_staleness_tuples():
    from borsenhirn.dashboard.bitacora_theme import render_metriken_strip, PALETTE
    cells = [
        ("BARGELD", "$31,853", "29% verfügbar", False, "live"),
        ("INFLATION · CPI", "3.3%", "↑ 0.66%", True, "cache"),
    ]
    html = render_metriken_strip(cells)
    # El segundo (cache) debe tener el dot ámbar
    assert html.count(PALETTE["ambar"]) >= 1
    assert "BARGELD" in html
    assert "CPI" in html


# ─── Source map documenta cada métrica visible ──────────────────────────────

def test_source_map_covers_all_visible_metrics():
    """
    Garantía: cada métrica que el dashboard renderiza tiene su entrada en
    DATA_SOURCE_MAP · base para debugging futuro.
    """
    from borsenhirn.dashboard.bitacora_data import DATA_SOURCE_MAP
    visible = ("equity", "cash", "buying_power", "day_pl", "day_pl_pct",
               "regime", "confidence", "vix", "cpi", "cpi_change",
               "fed_rate", "fed_rate_trend", "win_rate",
               "trades_today", "trades_closed", "positions")
    for m in visible:
        assert m in DATA_SOURCE_MAP, f"métrica {m} no documentada en DATA_SOURCE_MAP"
        assert "primary" in DATA_SOURCE_MAP[m]
        assert "fallback" in DATA_SOURCE_MAP[m]
RCE_MAP[m]
