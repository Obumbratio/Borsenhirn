"""
dashboard.py — Börsenhirn Dashboard · "Bitácora Nocturna" v1.1

v1.1 — Bugfixes post-deploy del rediseño:
   1. Datos: ahora usa borsenhirn.dashboard.bitacora_data.build_payload() que
      mergea /portfolio (fuente directa Alpaca) y /status, llama a
      m2_analyst.MacroFetcher para CPI/Fed Funds, cae a yFinance para VIX,
      y cachea en disco con indicador de frescura.
   2. HTML: eliminado el f-string indented que Streamlit estaba interpretando
      como bloque de código en el header de Täglicher Gewinn. Ahora se usa
      render_daily_pnl_header() del theme module · todo inline, sin newlines.
   3. Coherencia: equity, delta_pct y cumulative_pnl provienen de un unico
      DataPayload · no pueden desincronizarse.

Backend intacto: este archivo solo consume bot_api endpoints e imports
read-only. No toca trading logic, vault, tenancy, ML, ni schema.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from borsenhirn.dashboard.bitacora_data import build_payload, DATA_SOURCE_MAP
from borsenhirn.dashboard.bitacora_state import (
    current_eintrag,
    force_increment,
    session_metadata,
)
from borsenhirn.dashboard.bitacora_theme import (
    GLOBAL_CSS,
    PALETTE,
    chart_label,
    count_healthy,
    derive_module_statuses,
    plotly_layout,
    render_daily_pnl_header,
    render_disclaimer,
    render_exemplar_card,
    render_exemplare_header,
    render_exemplare_more,
    render_footer,
    render_hirn_bubble,
    render_hirn_header,
    render_kopfzeile,
    render_metriken_strip,
    render_observation_card,
    render_regime_gauge,
    render_regime_verlauf,
    render_sinapsen_grid,
    render_sinapsen_header,
    render_steuerung_header,
    render_vermoegen_card,
)
from borsenhirn.dashboard.bitacora_voice import (
    ObservationContext,
    get_observation,
    invalidate_cache as invalidate_observation_cache,
)

st.set_page_config(
    page_title="Bitácora · Börsenhirn",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

API_URL = os.environ.get("BORSENHIRN_API_URL", "http://localhost:8000")


@st.cache_data(ttl=30)
def get_payload():
    return build_payload()


st.markdown(render_disclaimer(), unsafe_allow_html=True)


payload = get_payload()
session_meta = session_metadata()
eintrag_n = session_meta["entry_number"]
days_in_paper = session_meta["days_since_first"] if payload.bot_mode != "LIVE" else None

st.markdown(
    render_kopfzeile(
        eintrag=eintrag_n,
        api_online=payload.api_online,
        alpaca_ok=payload.alpaca_ok,
        bot_mode=payload.bot_mode,
        days_in_paper=days_in_paper,
    ),
    unsafe_allow_html=True,
)

if not payload.api_online:
    st.markdown(
        f'<div style="background:{PALETTE["bg_tarjeta"]};'
        f'border-left:2px solid {PALETTE["rojo_terra"]};padding:14px 18px;'
        f'margin:18px 0;font-family:Georgia,serif;font-style:italic;'
        f'font-size:13.5px;color:{PALETTE["texto_perg"]};line-height:1.6">'
        f'"El cerebro está dormido. <span style=\'color:{PALETTE["rojo_terra"]}\'>'
        f'bot_api.py no responde.</span> Arrancá el backend con '
        f'<code style=\'font-family:Inter;font-size:11px\'>python bot_api.py</code>'
        f' y refrescá la bitácora."</div>',
        unsafe_allow_html=True,
    )
    st.stop()


positions_winning = sum(1 for p in payload.positions
                         if (p.get("unrealized_pl", 0) or 0) >= 0)
positions_losing = sum(1 for p in payload.positions
                        if (p.get("unrealized_pl", 0) or 0) < 0)

obs_ctx = ObservationContext(
    regime=payload.regime.value or "—",
    confidence=float(payload.confidence.value or 0),
    vix=float(payload.vix.value or 0),
    positions_open=len(payload.positions),
    positions_winning=positions_winning,
    positions_losing=positions_losing,
    net_pnl=float(payload.day_pl.value or 0),
    cumulative_pnl=float(payload.cumulative_pnl.value or 0),
    days_since_first=session_meta["days_since_first"],
    win_rate_pct=float(payload.win_rate.value or 0),
    new_positions_today=int(payload.trades_today.value or 0),
)
obs = get_observation(obs_ctx)

st.markdown(
    render_observation_card(
        text=obs["text"],
        confidence=obs_ctx.confidence,
        components_active=obs["components_active"],
        source=obs["source"],
    ),
    unsafe_allow_html=True,
)


# Spark + start label desde perf_history
spark_values = []
start_label = "—"
df_perf = None
if payload.perf_history and len(payload.perf_history) > 1:
    df_perf = pd.DataFrame(payload.perf_history)
    df_perf["date"] = pd.to_datetime(df_perf["date"])
    df_perf = df_perf.sort_values("date").reset_index(drop=True)
    spark_values = df_perf["equity"].tolist()
    first_dt = df_perf["date"].iloc[0]
    de_months = ["Januar","Februar","März","April","Mai","Juni",
                  "Juli","August","September","Oktober","November","Dezember"]
    start_label = f"{first_dt.day}. {de_months[first_dt.month - 1]}"

spark_x_labels = []
if df_perf is not None and spark_values and len(spark_values) >= 5:
    n = len(spark_values)
    idxs = [0, n // 4, n // 2, 3 * n // 4, n - 1]
    months_de = {3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN", 7: "JUL", 8: "AGO",
                 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC", 1: "ENE", 2: "FEB"}
    for i in idxs:
        d = df_perf["date"].iloc[i]
        spark_x_labels.append(f"{d.day:02d} {months_de[d.month]}")

equity_val = float(payload.equity.value or 0)
day_pl_pct_val = float(payload.day_pl_pct.value or 0)
cumulative_pnl_val = float(payload.cumulative_pnl.value or 0)

pct_change_total = day_pl_pct_val
if spark_values and spark_values[0] > 0:
    pct_change_total = (spark_values[-1] - spark_values[0]) / spark_values[0] * 100
if cumulative_pnl_val == 0 and spark_values and len(spark_values) > 1:
    cumulative_pnl_val = spark_values[-1] - spark_values[0]

col_v, col_g = st.columns([1.7, 1])
with col_v:
    st.markdown(
        render_vermoegen_card(
            equity=equity_val,
            pct_change=pct_change_total,
            cumulative_pnl=cumulative_pnl_val,
            start_date_label=start_label,
            sparkline_values=spark_values or [equity_val, equity_val],
            sparkline_x_labels=spark_x_labels,
            equity_stale=payload.equity.stale,
            equity_source=payload.equity.source,
        ),
        unsafe_allow_html=True,
    )

with col_g:
    st.markdown(
        render_regime_gauge(
            confidence=float(payload.confidence.value or 0),
            regime=str(payload.regime.value or "—"),
            days_28_pct=float(payload.confidence.value or 0) if payload.confidence.value else None,
            stale=payload.regime.stale,
            source=payload.regime.source,
        ),
        unsafe_allow_html=True,
    )

st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)


regime_history = []
if payload.perf_history:
    for entry in payload.perf_history:
        rg = (entry.get("regime") or "").upper()
        if rg in ("BULL", "BEAR", "SIDEWAYS", "PANIC"):
            regime_history.append(rg)
        else:
            pnl = entry.get("pnl", 0) or 0
            regime_history.append(
                "BULL" if pnl > 0 else ("BEAR" if pnl < 0 else "SIDEWAYS")
            )

if not regime_history:
    rg_now = str(payload.regime.value).upper() if payload.regime.value not in (None, "—") else "SIDEWAYS"
    regime_history = [rg_now] * 28

st.markdown(render_regime_verlauf(regime_history), unsafe_allow_html=True)


cash_val = float(payload.cash.value or 0)
n_positions = len(payload.positions)
trades_td = int(payload.trades_today.value or 0)
n_closed = int(payload.trades_closed.value or 0)
win_rate = float(payload.win_rate.value or 0)
vix_val = float(payload.vix.value or 0)
vix_state = "ruhig" if vix_val < 20 else ("mittel" if vix_val < 30 else "hoch")
cash_pct = (cash_val / equity_val * 100) if equity_val > 0 else 0

cpi_v = payload.cpi.value
cpi_chg = payload.cpi_change.value
fed_v = payload.fed_rate.value
fed_trend = payload.fed_rate_trend.value or "flat"
fed_arrow = {"rising": "↑", "falling": "↓", "flat": "→"}.get(fed_trend, "→")

cpi_sub = "esperando"
if cpi_chg is not None:
    cpi_sub = f"{'↑' if (cpi_chg or 0) >= 0 else '↓'} {abs(cpi_chg):.2f}%"
elif payload.cpi.error and "import" in (payload.cpi.error or ""):
    cpi_sub = "FRED · sin clave"

metrik_cells = [
    ("BARGELD",
     f"${cash_val:,.0f}" if cash_val else "—",
     f"{cash_pct:.0f}% verfügbar" if cash_val else "esperando",
     payload.cash.stale, payload.cash.source),
    ("POSITIONEN",
     f"{n_positions} / {payload.bot_watchlist_size}",
     "offen",
     False, "live"),
    ("SIEGRATE",
     f"{win_rate:.1f}%" if n_closed else "—",
     f"{int(payload.wins_today.value or 0)} / {n_closed} cerrados" if n_closed else "sin cerrar",
     payload.win_rate.stale, payload.win_rate.source),
    ("ANGST · VIX",
     f"{vix_val:.2f}" if vix_val else "—",
     f"→ {vix_state}" if vix_val else "esperando",
     payload.vix.stale, payload.vix.source),
    ("INFLATION · CPI",
     f"{cpi_v:.1f}%" if cpi_v not in (None, 0) else "—",
     cpi_sub,
     payload.cpi.stale, payload.cpi.source),
    ("LEITZINS · FED",
     f"{fed_v:.2f}%" if fed_v not in (None, 0) else "—",
     f"{fed_arrow} {fed_trend}" if fed_v else "esperando",
     payload.fed_rate.stale, payload.fed_rate.source),
]
st.markdown(render_metriken_strip(metrik_cells), unsafe_allow_html=True)


sorted_pos = sorted(
    payload.positions,
    key=lambda p: abs(float(p.get("unrealized_pl", 0) or 0)),
    reverse=True,
)
top_pos = sorted_pos[:6]
remaining = max(0, len(payload.positions) - 6)
net_pnl = sum(float(p.get("unrealized_pl", 0) or 0) for p in payload.positions)

st.markdown(
    render_exemplare_header(total=len(payload.positions), net_pnl=net_pnl),
    unsafe_allow_html=True,
)

if top_pos:
    cols = st.columns(3)
    for i, pos in enumerate(top_pos):
        with cols[i % 3]:
            st.markdown(
                render_exemplar_card(
                    symbol=pos.get("symbol", "—"),
                    qty=float(pos.get("qty", 0) or 0),
                    avg_entry=float(pos.get("avg_entry", 0) or 0),
                    last_price=float(pos.get("current_price", 0) or 0),
                    pnl=float(pos.get("unrealized_pl", 0) or 0),
                    pnl_pct=float(pos.get("unrealized_plpc", 0) or 0),
                ),
                unsafe_allow_html=True,
            )
    st.markdown(render_exemplare_more(remaining), unsafe_allow_html=True)
else:
    st.markdown(
        f'<div style="background:{PALETTE["bg_tarjeta"]};border:0.5px solid {PALETTE["linea"]};padding:24px;text-align:center;font-family:Georgia,serif;font-style:italic;font-size:13px;color:{PALETTE["texto_suave"]}">La cartera respira · cero exemplare hoy.</div>',
        unsafe_allow_html=True,
    )


st.markdown('<div style="margin-top:18px"></div>', unsafe_allow_html=True)

if payload.perf_history and df_perf is not None and len(df_perf) > 1:
    col_eq, col_pl = st.columns(2)

    with col_eq:
        st.markdown(chart_label("TÄGLICHE EQUITY", "por día"), unsafe_allow_html=True)
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=df_perf["date"],
            y=df_perf["equity"],
            mode="lines",
            line=dict(color=PALETTE["verde_oliva"], width=1.6,
                      shape="spline", smoothing=0.7),
            fill="tonexty",
            fillcolor="rgba(155,179,126,0.10)",
            hovertemplate="<b>%{x|%d %b}</b><br>$%{y:,.0f}<extra></extra>",
        ))
        if len(df_perf) > 1:
            fig_eq.add_hline(
                y=float(df_perf["equity"].iloc[0]),
                line_dash="dot",
                line_color=PALETTE["linea"],
                line_width=0.6,
            )
        fig_eq.update_layout(**plotly_layout(height=220, x_tickformat="%d %b"))
        st.plotly_chart(fig_eq, use_container_width=True)

    with col_pl:
        green_days = int((df_perf["pnl"] > 0).sum())
        red_days = int((df_perf["pnl"] < 0).sum())
        net_total = float(df_perf["pnl"].sum())

        # BUG 2 fix: header construido como string inline-only
        st.markdown(
            render_daily_pnl_header(
                de_label="TÄGLICHER GEWINN",
                es_label="P&amp;L diario",
                net_total=net_total,
                green_days=green_days,
                red_days=red_days,
            ),
            unsafe_allow_html=True,
        )

        bar_colors = [
            PALETTE["verde_oliva"] if v >= 0 else PALETTE["rojo_terra"]
            for v in df_perf["pnl"]
        ]
        fig_pnl = go.Figure(go.Bar(
            x=df_perf["date"], y=df_perf["pnl"],
            marker_color=bar_colors,
            marker_line_width=0,
            hovertemplate="<b>%{x|%d %b}</b><br>$%{y:,.0f}<extra></extra>",
        ))
        fig_pnl.add_hline(y=0, line_color=PALETTE["linea"], line_width=0.6)
        fig_pnl.update_layout(**plotly_layout(height=220, x_tickformat="%d %b"))
        st.plotly_chart(fig_pnl, use_container_width=True)


synthetic_status = {
    "bot": {"last_cycle": payload.bot_last_cycle,
            "watchlist_size": payload.bot_watchlist_size,
            "live_mode": payload.bot_mode == "LIVE"},
    "account": {"equity": payload.equity.value,
                "cash": payload.cash.value,
                "buying_power": payload.buying_power.value},
    "regime": {"regime": payload.regime.value,
               "confidence": payload.confidence.value,
               "vix": payload.vix.value},
    "memory": {"trades_today": payload.trades_today.value,
               "wins_today": payload.wins_today.value,
               "losses_today": payload.losses_today.value},
}
modules = derive_module_statuses(
    status_payload=synthetic_status,
    perf_payload={},
    trades_count=eintrag_n,
)
healthy = count_healthy(modules)
st.markdown(render_sinapsen_header(healthy=healthy, total=6), unsafe_allow_html=True)
st.markdown(render_sinapsen_grid(modules), unsafe_allow_html=True)


st.markdown(render_hirn_header(eintrag=eintrag_n), unsafe_allow_html=True)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


def _ask_hirn(message: str) -> str:
    try:
        result = subprocess.run(
            ["python", "m5_assistant.py", "--once", message],
            capture_output=True, text=True, timeout=60,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        return result.stdout.strip() or result.stderr.strip() or "Sin respuesta."
    except Exception as e:
        return f"Error invocando M5: {e}"


for msg in st.session_state.chat_history[-6:]:
    st.markdown(
        render_hirn_bubble(msg["role"], msg["content"]),
        unsafe_allow_html=True,
    )

user_msg = st.text_input(
    "Preguntale a Hirn",
    key="hirn_input",
    placeholder=("Pregúntale a Hirn — z.B. ¿qué hay en HD? · /analisis CVX · "
                 "/mejoras · wie ist meine siegrate?"),
    label_visibility="collapsed",
)

quick_commands = [
    ("▸ ANÁLISIS",   "/analisis"),
    ("▸ MEJORAS",    "/mejoras"),
    ("▸ SIEGRATE",   "¿Cuál es mi win rate histórico y cómo mejorarlo?"),
    ("▸ WALE",       "¿Qué oportunidades de whale copy son más relevantes ahora?"),
    ("▸ ALERTAS",    "¿Hay algo en el portafolio que debería atender urgentemente?"),
    ("▸ STRATEGIE",  "¿Qué estrategia recomiendas para el régimen actual?"),
]
pill_cols = st.columns(len(quick_commands) + 2)
with pill_cols[0]:
    if st.button("ENVIAR →", key="hirn_send", use_container_width=True):
        msg_to_send = user_msg.strip()
        if msg_to_send:
            with st.spinner("Hirn pensando..."):
                reply = _ask_hirn(msg_to_send)
            st.session_state.chat_history.append({"role": "user", "content": msg_to_send})
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()
with pill_cols[1]:
    if st.button("LIMPIAR", key="hirn_clear", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

for idx, (label, cmd) in enumerate(quick_commands):
    with pill_cols[idx + 2]:
        if st.button(label, key=f"quick_{idx}", use_container_width=True):
            with st.spinner("Hirn pensando..."):
                reply = _ask_hirn(cmd)
            st.session_state.chat_history.append({"role": "user", "content": cmd})
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()


st.markdown(render_steuerung_header(), unsafe_allow_html=True)

ctl_cols = st.columns([1, 1, 1, 1])
with ctl_cols[0]:
    if st.button("↻  AKTUALISIEREN · refrescar", key="ctl_refresh",
                 use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with ctl_cols[1]:
    if st.button("⚡  ZYKLUS ERZWINGEN · forzar ciclo", key="ctl_cycle",
                 use_container_width=True):
        try:
            r = requests.post(f"{API_URL}/cycle", timeout=10)
            if r.status_code == 200:
                force_increment()
                invalidate_observation_cache()
                st.success("Ciclo ejecutado.")
                st.cache_data.clear()
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"Error: HTTP {r.status_code}")
        except Exception as e:
            st.error(f"No se pudo conectar: {e}")
with ctl_cols[2]:
    if st.button("📖  PROTOKOLL · ver bitácora completa", key="ctl_protokoll",
                 use_container_width=True):
        with st.expander("Protokoll · todas las entradas (TODO sprint siguiente)",
                         expanded=True):
            if payload.trades:
                df_all = pd.DataFrame(payload.trades)
                cols_show = [c for c in
                             ["timestamp", "action", "symbol", "price", "qty",
                              "pnl", "reason"] if c in df_all.columns]
                st.dataframe(df_all[cols_show], use_container_width=True, height=320)
            else:
                st.markdown(
                    f'<div style="font-family:Georgia,serif;font-style:italic;color:{PALETTE["texto_suave"]}">Sin entradas registradas todavía.</div>',
                    unsafe_allow_html=True,
                )
with ctl_cols[3]:
    auto = st.checkbox("AUTO · 30s", value=False, key="ctl_auto")

if auto:
    time.sleep(30)
    st.cache_data.clear()
    st.rerun()


stale_metrics = payload.metrics_with_indicator()
if stale_metrics:
    st.markdown(
        f'<div style="font-family:Inter,sans-serif;font-size:9px;letter-spacing:1.5px;'
        f'color:{PALETTE["texto_suave"]};text-align:right;margin-top:14px;'
        f'text-transform:uppercase">● indicador ámbar · '
        f'{len(stale_metrics)} métrica(s) no-live · '
        f'{", ".join(stale_metrics[:3])}{" ..." if len(stale_metrics) > 3 else ""}</div>',
        unsafe_allow_html=True,
    )


st.markdown(render_footer(), unsafe_allow_html=True)
