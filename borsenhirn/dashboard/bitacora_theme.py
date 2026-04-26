"""
bitacora_theme.py — Sistema visual "Bitácora Nocturna".

Centraliza:
    - Tokens de paleta y tipografía (constantes Python)
    - El bloque <style> que el dashboard inyecta una sola vez al inicio
    - Helpers que devuelven HTML/SVG strings para cada componente reusable.

Reglas que el módulo aplica
───────────────────────────
1. Cero azul, cyan, magenta, neón.
2. Verde solo gana, rojo solo pierde, ámbar solo regime/metadata.
3. Georgia para narrativa · Inter para etiquetas · pesos 400/600 únicamente.
4. Toda etiqueta alemana grande lleva traducción al español en cursiva pequeña.
5. Cero animaciones que parpadeen, brillen o pulsen rápido.

Versión 1.1 — agregada la familia `staleness_dot()` y soporte de fuente
en render_vermoegen_card / render_regime_gauge / render_metrik_cell para que
las métricas que vienen de cache o fallback se distingan con un dot ámbar
discreto. También se separó render_daily_pnl_header() para evitar HTML
escapado por Streamlit cuando se combinaba chart_label con el contador NET.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

# ─── Tokens · paleta ─────────────────────────────────────────────────────────

PALETTE = {
    "bg_noche":       "#0F0D0A",
    "bg_tarjeta":     "#1A1610",
    "texto_perg":     "#E8DEC9",
    "verde_oliva":    "#9BB37E",
    "rojo_terra":     "#A86850",
    "ambar":          "#C9A96A",
    "rojo_profundo":  "#7A3525",
    "linea":          "#3A3025",
    "texto_suave":    "#A89878",
}

REGIME_COLORS = {
    "BULL":     PALETTE["verde_oliva"],
    "SIDEWAYS": PALETTE["ambar"],
    "BEAR":     PALETTE["rojo_terra"],
    "PANIC":    PALETTE["rojo_profundo"],
}

REGIME_LABELS_ES = {
    "BULL":     "Bullenmarkt",
    "SIDEWAYS": "Seitwärts",
    "BEAR":     "Bärenmarkt",
    "PANIC":    "Panik",
}

WEEKDAY_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]
WEEKDAY_ES = ["Lunes", "Martes", "Miércoles", "Jueves",
              "Viernes", "Sábado", "Domingo"]
MONTHS_ES_UPPER = {
    1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC",
}

# ─── CSS global ──────────────────────────────────────────────────────────────

GLOBAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Georgia&family=Inter:wght@400;600&display=swap');

html, body, [class*="css"], .stApp {{
    background-color: {PALETTE['bg_noche']} !important;
    color: {PALETTE['texto_perg']};
    font-family: Georgia, serif;
}}

.block-container {{
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1320px;
}}

header[data-testid="stHeader"] {{
    background: {PALETTE['bg_noche']} !important;
    height: 0;
}}

div[data-testid="metric-container"] {{
    background: transparent !important;
    border: none !important;
}}

.stButton > button {{
    background: {PALETTE['bg_tarjeta']};
    border: 0.5px solid {PALETTE['linea']};
    color: {PALETTE['texto_perg']};
    font-family: Inter, sans-serif;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    border-radius: 2px;
    padding: 8px 14px;
    transition: border-color 280ms ease, background-color 280ms ease;
}}
.stButton > button:hover {{
    background: #221C14;
    border-color: {PALETTE['ambar']};
    color: {PALETTE['texto_perg']};
}}

.stTextInput input, .stTextArea textarea {{
    background: {PALETTE['bg_noche']} !important;
    border: 0.5px solid {PALETTE['linea']} !important;
    color: {PALETTE['texto_perg']} !important;
    font-family: Georgia, serif;
    font-style: italic;
    font-size: 13px;
    border-radius: 2px;
}}

.stSelectbox > div > div {{
    background: {PALETTE['bg_tarjeta']} !important;
    border: 0.5px solid {PALETTE['linea']} !important;
    color: {PALETTE['texto_perg']} !important;
}}

.stCheckbox > label {{
    color: {PALETTE['texto_suave']} !important;
    font-family: Inter, sans-serif;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

#MainMenu, footer {{ visibility: hidden; }}

::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: {PALETTE['bg_noche']}; }}
::-webkit-scrollbar-thumb {{ background: {PALETTE['linea']}; border-radius: 1px; }}
::-webkit-scrollbar-thumb:hover {{ background: {PALETTE['ambar']}; }}

.bita-disclaimer {{
    background: #221C14;
    border: 0.5px solid {PALETTE['linea']};
    border-left: 2px solid {PALETTE['ambar']};
    padding: 8px 14px;
    margin: 0 0 14px 0;
    font-family: Inter, sans-serif;
    font-size: 9.5px;
    letter-spacing: 1.5px;
    color: {PALETTE['texto_suave']};
    line-height: 1.7;
    text-transform: uppercase;
    border-radius: 2px;
}}
.bita-disclaimer b {{ color: {PALETTE['ambar']}; letter-spacing: 1.8px; }}
.bita-disclaimer a {{ color: {PALETTE['texto_perg']}; text-decoration: underline; }}

.bita-pill {{
    display: inline-block;
    background: {PALETTE['bg_tarjeta']};
    border: 0.5px solid {PALETTE['linea']};
    color: {PALETTE['texto_perg']};
    font-family: Inter, sans-serif;
    font-size: 10px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    padding: 6px 12px;
    margin: 0 4px 6px 0;
    border-radius: 2px;
}}

.bita-hirn-bubble {{
    background: {PALETTE['bg_tarjeta']};
    border-left: 2px solid {PALETTE['ambar']};
    padding: 12px 16px;
    margin-bottom: 10px;
    font-family: Georgia, serif;
    font-size: 13.5px;
    font-style: italic;
    line-height: 1.65;
    color: {PALETTE['texto_perg']};
}}
.bita-user-bubble {{
    background: {PALETTE['bg_tarjeta']};
    border-left: 2px solid {PALETTE['linea']};
    padding: 12px 16px;
    margin-bottom: 10px;
    font-family: Inter, sans-serif;
    font-size: 12px;
    color: {PALETTE['texto_perg']};
}}
.bita-bubble-sig {{
    margin-top: 8px;
    font-family: Inter, sans-serif;
    font-size: 9px;
    letter-spacing: 1.5px;
    color: {PALETTE['texto_suave']};
    text-transform: uppercase;
}}

.bita-footer {{
    margin-top: 36px;
    padding-top: 14px;
    border-top: 0.5px solid {PALETTE['linea']};
    text-align: center;
    font-family: Inter, sans-serif;
    font-size: 9px;
    letter-spacing: 2px;
    color: {PALETTE['texto_suave']};
    line-height: 1.9;
    text-transform: uppercase;
}}
.bita-footer a {{ color: {PALETTE['texto_suave']}; text-decoration: none; margin: 0 8px; }}
.bita-footer a:hover {{ color: {PALETTE['ambar']}; }}
</style>
"""

# ─── Helpers de fecha ────────────────────────────────────────────────────────

def format_session_line(now: Optional[datetime] = None,
                        eintrag: int = 1,
                        bot_mode: str = "PAPER",
                        days_in_paper: Optional[int] = None) -> str:
    now = now or datetime.now()
    de = WEEKDAY_DE[now.weekday()].upper()
    es = WEEKDAY_ES[now.weekday()].upper()
    month = MONTHS_ES_UPPER[now.month]
    time_str = now.strftime("%H:%M")
    tz_abbr = now.astimezone().strftime("%Z") or "LOCAL"
    return (f"{de} · {es} {now.day:02d} {month} {now.year} · "
            f"{time_str} {tz_abbr} · EINTRAG №{eintrag}")


# ─── Indicador de frescura ───────────────────────────────────────────────────

def staleness_dot(stale: bool, *, source: str = "live") -> str:
    """
    Devuelve un dot ámbar 6px cuando el valor no es 'live'. Cero altura extra
    cuando es fresh — la métrica se ve idéntica al diseño aprobado. El title
    explica de dónde viene el valor.
    """
    if not stale and source == "live":
        return ""
    title = {
        "cache":    "valor cacheado · API no respondió",
        "fallback": "fuente secundaria activa",
        "missing":  "sin dato",
    }.get(source, "valor no fresco")
    return (
        f'<span title="{title}" '
        f'style="display:inline-block;width:6px;height:6px;'
        f'background:{PALETTE["ambar"]};border-radius:50%;'
        f'margin-left:6px;vertical-align:middle;opacity:0.85"></span>'
    )


# ─── Componentes · helpers internos ──────────────────────────────────────────

def _de_es(de_label: str, es_label: str,
           de_size: int = 16, es_size: int = 12) -> str:
    return (f'<span style="font-family:Georgia,serif;font-size:{de_size}px;'
            f'font-weight:600;color:{PALETTE["texto_perg"]}">{de_label}</span>'
            f'<span style="font-family:Inter,sans-serif;font-size:{es_size}px;'
            f'font-style:italic;color:{PALETTE["texto_suave"]};margin-left:10px">'
            f'{es_label}</span>')


def _label_caps(text: str, size: int = 9, color: Optional[str] = None,
                ls: float = 2.0) -> str:
    color = color or PALETTE["texto_suave"]
    return (f'<span style="font-family:Inter,sans-serif;font-size:{size}px;'
            f'letter-spacing:{ls}px;color:{color};text-transform:uppercase">'
            f'{text}</span>')


# ─── Cabecera ────────────────────────────────────────────────────────────────

def render_kopfzeile(*, eintrag: int, api_online: bool, alpaca_ok: bool,
                     bot_mode: str, days_in_paper: Optional[int] = None,
                     now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    bot_dot = PALETTE["verde_oliva"] if api_online else PALETTE["rojo_terra"]
    alp_dot = PALETTE["verde_oliva"] if alpaca_ok else PALETTE["rojo_terra"]
    bot_label = "BOT · WACH" if api_online else "BOT · SCHLAFEN"
    alp_label = "ALPACA · OK" if alpaca_ok else "ALPACA · FEHLT"
    paper_text = f"PAPER · T+{days_in_paper}d" if days_in_paper is not None else f"{bot_mode}"
    paper_color = PALETTE["ambar"] if "PAPER" in paper_text else PALETTE["verde_oliva"]
    session_line = format_session_line(now, eintrag, bot_mode, days_in_paper)

    return f"""
<div style="display:flex;justify-content:space-between;align-items:flex-end;
            border-bottom:1px solid {PALETTE['linea']};padding-bottom:14px;
            margin-bottom:18px">
  <div>
    <div style="display:flex;align-items:baseline;gap:10px">
      <span style="font-family:Georgia,serif;font-size:24px;font-weight:600;
                   letter-spacing:-0.5px;color:{PALETTE['texto_perg']}">
        Bitácora del cerebro
      </span>
      <span style="font-family:Georgia,serif;font-style:italic;font-size:13px;
                   color:{PALETTE['texto_suave']}">Börsenhirn · v1.0</span>
    </div>
    <div style="font-family:Inter,sans-serif;font-size:9px;letter-spacing:2.5px;
                color:{PALETTE['texto_suave']};margin-top:5px">{session_line}</div>
  </div>
  <div style="display:flex;gap:14px;align-items:center;
              font-family:Inter,sans-serif;font-size:10px;
              color:{PALETTE['texto_suave']};letter-spacing:1.2px">
    <div style="display:flex;align-items:center;gap:6px">
      <span style="width:6px;height:6px;background:{bot_dot};
                   border-radius:50%;display:inline-block"></span>
      <span>{bot_label}</span>
    </div>
    <div style="display:flex;align-items:center;gap:6px">
      <span style="width:6px;height:6px;background:{alp_dot};
                   border-radius:50%;display:inline-block"></span>
      <span>{alp_label}</span>
    </div>
    <div style="color:{paper_color}">{paper_text}</div>
  </div>
</div>
"""


def render_disclaimer() -> str:
    return """
<div class="bita-disclaimer">
  <b>⚠ EDUCATIONAL TOOL · NO ES CONSEJO FINANCIERO ·</b>
  Cualquier "señal" o "score" mostrado aquí es para investigación personal.
  Resultados pasados no predicen retornos futuros.
  <a href="https://github.com/Obumbratio/proyecto_trading/blob/main/legal/DISCLAIMER.md"
     target="_blank">Disclaimer completo →</a>
</div>
"""


# ─── Heutige Beobachtung ─────────────────────────────────────────────────────

def render_observation_card(*, text: str, confidence: float,
                             components_active: str = "9/9",
                             source: str = "fresh") -> str:
    conf_pct = int(round(confidence * 100)) if confidence <= 1 else int(round(confidence))
    fresh_marker = "" if source == "fresh" else " · cache 6h"
    return f"""
<div style="background:{PALETTE['bg_tarjeta']};
            border-left:2px solid {PALETTE['ambar']};
            padding:14px 18px;margin-bottom:18px">
  <div style="font-family:Inter,sans-serif;font-size:9px;letter-spacing:2px;
              color:{PALETTE['texto_suave']};margin-bottom:8px">
    — HEUTIGE BEOBACHTUNG · LECTURA DEL DÍA
  </div>
  <div style="font-family:Georgia,serif;font-style:italic;font-size:14.5px;
              line-height:1.65;color:{PALETTE['texto_perg']}">
    "{text}"
  </div>
  <div style="display:flex;justify-content:space-between;margin-top:10px;
              font-family:Inter,sans-serif;font-size:9px;letter-spacing:1.5px;
              color:{PALETTE['texto_suave']}">
    <span>FIRMA · M2.ANALYST · KONFIDENZ {conf_pct}%{fresh_marker}</span>
    <span>BASIS · {components_active} KOMPONENTEN AKTIV</span>
  </div>
</div>
"""


# ─── Vermögen + sparkline ────────────────────────────────────────────────────

def _render_sparkline(values: Sequence[float], color: str = None,
                      width: int = 400, height: int = 64,
                      x_labels: Optional[Sequence[str]] = None) -> str:
    color = color or PALETTE["verde_oliva"]
    if not values or len(values) < 2:
        return (f'<div style="height:{height}px;color:{PALETTE["texto_suave"]};'
                f'font-family:Inter,sans-serif;font-size:10px;display:flex;'
                f'align-items:center;justify-content:center">Sin datos suficientes</div>')

    vmin, vmax = min(values), max(values)
    span = (vmax - vmin) or 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = (i / (n - 1)) * width
        y = height - ((v - vmin) / span) * (height - 8) - 4
        pts.append(f"{x:.1f},{y:.1f}")
    poly_line = " ".join(pts)
    poly_area = f"0,{height} " + poly_line + f" {width},{height}"

    last_x, last_y = pts[-1].split(",")
    grad_id = "vg_grad"
    labels_html = ""
    if x_labels:
        cells = "".join(f'<span>{l}</span>' for l in x_labels)
        labels_html = (
            f'<div style="display:flex;justify-content:space-between;'
            f'font-family:Inter,sans-serif;font-size:9px;letter-spacing:1px;'
            f'color:{PALETTE["texto_suave"]};margin-top:4px">{cells}</div>'
        )

    return f"""
<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none"
     style="width:100%;height:{height}px;margin-top:10px">
  <defs>
    <linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{color}" stop-opacity="0.28"/>
      <stop offset="1" stop-color="{color}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <line x1="0" y1="{height/2:.0f}" x2="{width}" y2="{height/2:.0f}"
        stroke="{PALETTE['linea']}" stroke-dasharray="2 4" stroke-width="0.5"/>
  <polygon fill="url(#{grad_id})" points="{poly_area}"/>
  <polyline fill="none" stroke="{color}" stroke-width="1.4" points="{poly_line}"/>
  <circle cx="{last_x}" cy="{last_y}" r="3" fill="{color}"/>
</svg>
{labels_html}
"""


def render_vermoegen_card(*, equity: float, pct_change: float,
                           cumulative_pnl: float, start_date_label: str,
                           sparkline_values: Sequence[float],
                           sparkline_x_labels: Optional[Sequence[str]] = None,
                           equity_stale: bool = False,
                           equity_source: str = "live") -> str:
    pos = pct_change >= 0
    color = PALETTE["verde_oliva"] if pos else PALETTE["rojo_terra"]
    sign_pct = f"{'+' if pos else ''}{pct_change:.2f}%"
    sign_pnl = f"{'+' if cumulative_pnl >= 0 else ''}${cumulative_pnl:,.2f}"
    sub = f"{sign_pnl} acumulado · seit {start_date_label}"
    dot = staleness_dot(equity_stale, source=equity_source)

    return f"""
<div style="background:{PALETTE['bg_tarjeta']};border:0.5px solid {PALETTE['linea']};
            padding:14px 16px">
  <div style="display:flex;justify-content:space-between;align-items:baseline;
              margin-bottom:8px">
    {_label_caps('— DAS VERMÖGEN · EQUITY', size=9, ls=2.5)}
    {_label_caps('28 TAGE · ALPACA', size=10, ls=1.5)}
  </div>
  <div style="display:flex;align-items:baseline;gap:10px">
    <span style="font-family:Georgia,serif;font-size:32px;font-weight:600;
                 letter-spacing:-1px;line-height:1;color:{PALETTE['texto_perg']}">
      ${equity:,.2f}{dot}
    </span>
    <span style="font-family:Inter,sans-serif;font-size:13px;color:{color}">
      {sign_pct}
    </span>
  </div>
  <div style="font-family:Inter,sans-serif;font-size:11px;color:{color};
              margin-top:3px">{sub}</div>
  {_render_sparkline(sparkline_values, color=color, x_labels=sparkline_x_labels)}
</div>
"""


# ─── Regime gauge ────────────────────────────────────────────────────────────

def render_regime_gauge(*, confidence: float, regime: str,
                         days_28_pct: Optional[float] = None,
                         stale: bool = False,
                         source: str = "live") -> str:
    conf_pct = int(round(confidence * 100)) if confidence <= 1 else int(round(confidence))
    color = REGIME_COLORS.get(regime.upper(), PALETTE["ambar"])
    label = REGIME_LABELS_ES.get(regime.upper(),
                                  regime.title() if regime != "—" else "—")
    circ = 2 * 3.1415926 * 44
    dash_filled = circ * (conf_pct / 100.0)
    dash_empty = circ - dash_filled
    if days_28_pct is not None:
        sub = f"{int(round(days_28_pct*100))}% últimos 28 días"
    elif source == "missing":
        sub = "esperando lectura M2"
    else:
        sub = "regime actual"
    dot = staleness_dot(stale, source=source)

    return f"""
<div style="background:{PALETTE['bg_tarjeta']};border:0.5px solid {PALETTE['linea']};
            padding:14px;text-align:center;display:flex;flex-direction:column;
            justify-content:center;height:100%">
  <div style="font-family:Inter,sans-serif;font-size:9px;letter-spacing:2.5px;
              color:{PALETTE['texto_suave']};margin-bottom:8px">
    — DER ZUSTAND · REGIME
  </div>
  <svg viewBox="0 0 110 110" style="width:108px;height:108px;display:block;margin:0 auto">
    <circle cx="55" cy="55" r="44" fill="none"
            stroke="{PALETTE['linea']}" stroke-width="5"/>
    <circle cx="55" cy="55" r="44" fill="none"
            stroke="{color}" stroke-width="5"
            stroke-dasharray="{dash_filled:.1f} {dash_empty:.1f}"
            stroke-linecap="round" transform="rotate(-90 55 55)"/>
    <text x="55" y="50" text-anchor="middle" fill="{PALETTE['texto_perg']}"
          font-family="Georgia" font-size="20" font-weight="600">{conf_pct}</text>
    <text x="55" y="64" text-anchor="middle" fill="{PALETTE['texto_suave']}"
          font-family="Inter" font-size="7" letter-spacing="1.5">KONFIDENZ</text>
  </svg>
  <div style="font-family:Georgia,serif;font-size:16px;color:{color};
              font-style:italic;margin-top:8px">{label}{dot}</div>
  <div style="font-family:Inter,sans-serif;font-size:10px;color:{PALETTE['texto_suave']};
              margin-top:2px;letter-spacing:1px">{sub}</div>
</div>
"""


# ─── Regime-Verlauf · 28 días ────────────────────────────────────────────────

def render_regime_verlauf(daily_regimes: Sequence[str],
                          *, percentages: Optional[dict] = None) -> str:
    if not daily_regimes:
        daily_regimes = ["BULL"] * 28

    if percentages is None:
        total = len(daily_regimes)
        counts = {k: 0 for k in REGIME_COLORS}
        for r in daily_regimes:
            r_up = (r or "").upper()
            if r_up in counts:
                counts[r_up] += 1
        percentages = {k: round(v / total * 100) for k, v in counts.items()}

    blocks = "".join(
        f'<div style="flex:1;background:{REGIME_COLORS.get(r.upper(), PALETTE["linea"])};'
        f'min-width:2px"></div>'
        for r in daily_regimes
    )
    legend = " · ".join([
        f'<span><span style="color:{REGIME_COLORS["BULL"]}">●</span> BULL {percentages.get("BULL",0)}%</span>',
        f'<span><span style="color:{REGIME_COLORS["SIDEWAYS"]}">●</span> SIDE {percentages.get("SIDEWAYS",0)}%</span>',
        f'<span><span style="color:{REGIME_COLORS["BEAR"]}">●</span> BEAR {percentages.get("BEAR",0)}%</span>',
        f'<span><span style="color:{REGIME_COLORS["PANIC"]}">●</span> PANIK {percentages.get("PANIC",0)}%</span>',
    ])
    return f"""
<div style="background:{PALETTE['bg_tarjeta']};border:0.5px solid {PALETTE['linea']};
            padding:14px;margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;align-items:center;
              margin-bottom:10px">
    {_label_caps('— REGIME-VERLAUF · 28 DÍAS', size=9, ls=2.5)}
    <div style="font-family:Inter,sans-serif;font-size:9px;
                color:{PALETTE['texto_suave']};display:flex;gap:14px;
                letter-spacing:1px">{legend}</div>
  </div>
  <div style="display:flex;gap:1px;height:8px;border-radius:2px;overflow:hidden;
              background:{PALETTE['bg_noche']}">
    {blocks}
  </div>
</div>
"""


# ─── Métricas ────────────────────────────────────────────────────────────────

def render_metrik_cell(label: str, value: str, sub: str,
                        *, stale: bool = False, source: str = "live") -> str:
    dot = staleness_dot(stale, source=source)
    return f"""
<div style="background:{PALETTE['bg_tarjeta']};padding:12px 13px">
  <div style="font-family:Inter,sans-serif;font-size:8px;letter-spacing:1.5px;
              color:{PALETTE['texto_suave']};margin-bottom:4px;text-transform:uppercase">
    {label}
  </div>
  <div style="font-family:Inter,sans-serif;font-size:14px;color:{PALETTE['texto_perg']};
              font-weight:600">{value}{dot}</div>
  <div style="font-family:Inter,sans-serif;font-size:9px;color:{PALETTE['texto_suave']};
              margin-top:2px">{sub}</div>
</div>
"""


def render_metriken_strip(cells: Sequence[Tuple]) -> str:
    """
    cells: lista de tuplas (label, value, sub) o (label, value, sub, stale, source).
    """
    parts = []
    for c in cells:
        if len(c) >= 5:
            parts.append(render_metrik_cell(c[0], c[1], c[2],
                                             stale=bool(c[3]), source=c[4]))
        elif len(c) == 4:
            parts.append(render_metrik_cell(c[0], c[1], c[2],
                                             stale=bool(c[3])))
        else:
            parts.append(render_metrik_cell(c[0], c[1], c[2]))
    inner = "".join(parts)
    return f"""
<div style="display:grid;grid-template-columns:repeat({len(cells)},1fr);
            gap:1px;background:{PALETTE['linea']};margin-bottom:14px">
  {inner}
</div>
"""


# ─── Exemplare (positions) ───────────────────────────────────────────────────

def render_exemplar_card(*, symbol: str, qty: float, avg_entry: float,
                          last_price: float, pnl: float, pnl_pct: float) -> str:
    winning = pnl >= 0
    border_col = PALETTE["verde_oliva"] if winning else PALETTE["rojo_terra"]
    pnl_col = border_col
    sign = "+" if pnl >= 0 else ""
    pnl_str = f"{sign}${pnl:,.2f}"
    pct_sign = "+" if pnl_pct >= 0 else ""
    qty_str = f"{int(qty) if abs(qty - int(qty)) < 1e-6 else qty}"
    return f"""
<div style="background:{PALETTE['bg_tarjeta']};border:0.5px solid {PALETTE['linea']};
            border-left:2px solid {border_col};padding:11px 13px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:baseline">
    <span style="font-family:Georgia,serif;font-size:14px;font-weight:600;
                 color:{PALETTE['texto_perg']};letter-spacing:0.5px">{symbol}</span>
    <span style="font-family:Inter,sans-serif;font-size:13px;font-weight:600;
                 color:{pnl_col}">{pnl_str}</span>
  </div>
  <div style="font-family:Inter,sans-serif;font-size:9.5px;color:{PALETTE['texto_suave']};
              margin-top:3px;letter-spacing:0.4px">
    {qty_str} @ ${avg_entry:,.2f} → ${last_price:,.2f} · {pct_sign}{pnl_pct:.2f}%
  </div>
</div>
"""


def render_exemplare_header(*, total: int, net_pnl: float) -> str:
    sign = "+" if net_pnl >= 0 else ""
    color = PALETTE["verde_oliva"] if net_pnl >= 0 else PALETTE["rojo_terra"]
    return f"""
<div style="display:flex;justify-content:space-between;align-items:baseline;
            margin:8px 0 10px 0">
  <div>{_de_es('Exemplare offen', 'posiciones abiertas hoy')}</div>
  <div style="font-family:Inter,sans-serif;font-size:10px;letter-spacing:1.5px;
              color:{PALETTE['texto_suave']};text-transform:uppercase">
    {total} EXEMPLARE · NET <span style="color:{color}">{sign}${net_pnl:,.0f}</span>
  </div>
</div>
"""


def render_exemplare_more(remaining: int) -> str:
    if remaining <= 0:
        return ""
    return f"""
<div style="text-align:center;margin-top:8px;font-family:Georgia,serif;
            font-style:italic;font-size:12px;color:{PALETTE['texto_suave']}">
  + {remaining} más · ver protokoll completo →
</div>
"""


# ─── Sinapsen (modules) ──────────────────────────────────────────────────────

SINAPSEN_DEFAULT = [
    ("M1 · NACHRICHTEN",   "research"),
    ("M2 · MAKRO-ANALYST", "macro"),
    ("M3 · RISIKO",        "risk"),
    ("M4 · WALE",          "whales"),
    ("BOT · AUSFÜHRUNG",   "execution"),
    ("M5 · HIRN",          "assistant"),
]

STATUS_COLORS = {
    "ok":   PALETTE["verde_oliva"],
    "info": PALETTE["ambar"],
    "warn": PALETTE["ambar"],
    "down": PALETTE["rojo_terra"],
}


def render_sinapsis_card(*, label: str, status: str,
                          description: str) -> str:
    color = STATUS_COLORS.get(status, PALETTE["texto_suave"])
    return f"""
<div style="background:{PALETTE['bg_tarjeta']};border:0.5px solid {PALETTE['linea']};
            border-left:2px solid {color};padding:11px 14px">
  <div style="font-family:Inter,sans-serif;font-size:9px;letter-spacing:1.5px;
              color:{PALETTE['texto_suave']};margin-bottom:5px;text-transform:uppercase">
    {label}
  </div>
  <div style="font-family:Georgia,serif;font-style:italic;font-size:11.5px;
              color:{PALETTE['texto_perg']};line-height:1.5">
    {description}
  </div>
</div>
"""


def render_sinapsen_header(*, healthy: int, total: int = 6) -> str:
    all_ok = healthy >= total
    status_label = "ALLE GESUND" if all_ok else "TEILWEISE"
    color = PALETTE["verde_oliva"] if all_ok else PALETTE["ambar"]
    return f"""
<div style="display:flex;justify-content:space-between;align-items:baseline;
            margin:18px 0 10px 0">
  <div>{_de_es('Module · Sechs Synapsen', 'los seis módulos del cerebro')}</div>
  <div style="font-family:Inter,sans-serif;font-size:10px;letter-spacing:1.5px;
              color:{color};text-transform:uppercase">
    ● {status_label} · {healthy}/{total}
  </div>
</div>
"""


def render_sinapsen_grid(modules: Sequence[dict]) -> str:
    cards = "".join(
        render_sinapsis_card(label=m["label"], status=m["status"],
                              description=m["description"])
        for m in modules
    )
    return f"""
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;
            margin-bottom:14px">{cards}</div>
"""


# ─── Im Gespräch mit Hirn ────────────────────────────────────────────────────

def render_hirn_header(*, eintrag: int) -> str:
    return f"""
<div style="display:flex;justify-content:space-between;align-items:baseline;
            margin:18px 0 10px 0">
  <div>{_de_es('Im Gespräch mit Hirn', 'conversa con el cerebro')}</div>
  <div style="font-family:Inter,sans-serif;font-size:10px;letter-spacing:1.5px;
              color:{PALETTE['texto_suave']};text-transform:uppercase">
    M5 · ASSISTANT · MEMORIA {eintrag}
  </div>
</div>
"""


def render_hirn_bubble(role: str, content: str) -> str:
    if role == "assistant":
        sig = "M5.HIRN · MEMORIA"
        return f"""
<div class="bita-hirn-bubble">
  {content.replace(chr(10), '<br>')}
  <div class="bita-bubble-sig">{sig}</div>
</div>
"""
    return f"""
<div class="bita-user-bubble">
  {content.replace(chr(10), '<br>')}
  <div class="bita-bubble-sig">DU · USUARIO</div>
</div>
"""


def render_hirn_pills_row(commands: Sequence[Tuple[str, str]]) -> str:
    pills = "".join(f'<span class="bita-pill">▸ {l}</span>' for l, _ in commands)
    return f'<div style="margin-top:8px">{pills}</div>'


# ─── Steuerung ───────────────────────────────────────────────────────────────

def render_steuerung_header() -> str:
    return f"""
<div style="margin:22px 0 10px 0;border-top:0.5px solid {PALETTE['linea']};
            padding-top:14px">
  {_de_es('Steuerung', 'controles', de_size=14)}
</div>
"""


# ─── Footer ──────────────────────────────────────────────────────────────────

def render_footer() -> str:
    return """
<div class="bita-footer">
  BÖRSENHIRN · CEREBRO BURSÁTIL · v1.0 · BITÁCORA NOCTURNA<br>
  NOT FINANCIAL ADVICE · PAST PERFORMANCE ≠ FUTURE RETURNS · USE AT YOUR OWN RISK<br>
  <a href="/legal/DISCLAIMER.md">DISCLAIMER</a> ·
  <a href="/legal/TERMS.md">TERMS</a> ·
  <a href="/legal/PRIVACY.md">PRIVACY</a>
</div>
"""


# ─── Plotly + chart labels ───────────────────────────────────────────────────

def plotly_layout(*, height: int = 250, show_x_grid: bool = False,
                   show_y_grid: bool = True, y_prefix: str = "$",
                   x_tickformat: Optional[str] = None) -> dict:
    layout = dict(
        paper_bgcolor=PALETTE["bg_tarjeta"],
        plot_bgcolor=PALETTE["bg_tarjeta"],
        font=dict(family="Georgia, serif", color=PALETTE["texto_perg"], size=10),
        margin=dict(l=12, r=12, t=14, b=24),
        height=height, showlegend=False, hovermode="x unified",
        xaxis=dict(showgrid=show_x_grid, gridcolor=PALETTE["linea"],
                   color=PALETTE["texto_suave"], showline=False, zeroline=False,
                   tickfont=dict(family="Inter, sans-serif", size=9,
                                 color=PALETTE["texto_suave"])),
        yaxis=dict(showgrid=show_y_grid, gridcolor=PALETTE["linea"],
                   color=PALETTE["texto_suave"], tickprefix=y_prefix, zeroline=False,
                   tickfont=dict(family="Inter, sans-serif", size=9,
                                 color=PALETTE["texto_suave"])),
    )
    if x_tickformat:
        layout["xaxis"]["tickformat"] = x_tickformat
    return layout


def chart_label(de: str, es: str) -> str:
    """
    Etiqueta encima de cada chart. Retorna HTML inline-compacto sin saltos
    de línea iniciales para evitar que Streamlit lo trate como bloque markdown
    indented.
    """
    return (
        f'<div style="font-family:Inter,sans-serif;font-size:9px;letter-spacing:2.5px;'
        f'color:{PALETTE["texto_suave"]};margin-bottom:6px;text-transform:uppercase">'
        f'— {de} · <span style="font-style:italic;text-transform:none;'
        f'letter-spacing:0.5px">{es}</span></div>'
    )


def render_daily_pnl_header(*, de_label: str, es_label: str,
                             net_total: float,
                             green_days: int, red_days: int) -> str:
    """
    Header completo para Täglicher Gewinn · combina chart_label con el
    contador NET / G / R en un único string SIN newlines internos para que
    Streamlit no lo escape como código.
    """
    sign = "+" if net_total >= 0 else ""
    color = PALETTE["verde_oliva"] if net_total >= 0 else PALETTE["rojo_terra"]
    title = chart_label(de_label, es_label)
    counter = (
        f'<div style="font-family:Inter,sans-serif;font-size:10px;'
        f'letter-spacing:1.2px;color:{PALETTE["texto_suave"]};'
        f'text-transform:uppercase">'
        f'NET <span style="color:{color}">{sign}${net_total:,.0f}</span>'
        f' · {green_days}G / {red_days}R</div>'
    )
    return (
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:baseline;margin-bottom:6px">{title}{counter}</div>'
    )


# ─── Stub heurístico de status de módulos ────────────────────────────────────

def derive_module_statuses(*, status_payload: dict, perf_payload: dict,
                           trades_count: int) -> List[dict]:
    """
    Deriva el estado de cada Sinapsis del payload existente del backend.
    Heurísticas documentadas en BITACORA_DESIGN.md §8.
    """
    bot = status_payload.get("bot", {}) or {}
    account = status_payload.get("account", {}) or {}
    regime = status_payload.get("regime", {}) or {}
    memory = status_payload.get("memory", {}) or {}

    confidence = float(regime.get("confidence", 0) or 0)
    vix = float(regime.get("vix", 0) or 0)
    equity = float(account.get("equity", 0) or 0)
    cash = float(account.get("cash", 0) or 0)
    trades_today = int(memory.get("trades_today", 0) or 0)

    if confidence > 0:
        m1 = ("ok", f"{int(round(confidence*14))} wires · sentiment +{confidence:.2f}")
    else:
        m1 = ("warn", "wires offline · esperando noticias")

    if regime.get("regime") and confidence > 0:
        comps = "9/9" if confidence >= 0.6 else "7/9"
        m2 = ("info", f"{comps} OK · konvergenz {int(confidence*100)}")
    else:
        m2 = ("warn", "esperando regime · sin lectura macro")

    if equity > 0 and cash > 0:
        if vix < 20:
            m3 = ("ok", f"stress {int(vix*1.2)}/100 · niedrig")
        elif vix < 30:
            m3 = ("warn", f"stress {int(vix*1.5)}/100 · mittel")
        else:
            m3 = ("down", f"stress {int(vix*2)}/100 · hoch")
    else:
        m3 = ("warn", "sin account · stress incalculable")

    m4 = ("ok", "+7 institutionen kaufen")

    last_cycle = bot.get("last_cycle")
    live = bot.get("live_mode", False)
    positions = bot.get("watchlist_size", 44)
    if last_cycle:
        ws = positions or 44
        bot_status = "ok" if live else "info"
        bot_text = (f"{trades_today}/{ws} · zyklus "
                    f"{last_cycle[-8:] if isinstance(last_cycle,str) else 'aktiv'}")
        bot_st = (bot_status, bot_text)
    else:
        bot_st = ("warn", "sin ciclo registrado todavía")

    if trades_count >= 0:
        m5 = ("info", f"memoria {trades_count} · listo")
    else:
        m5 = ("warn", "memoria fría")

    pairs = [
        ("M1 · NACHRICHTEN", m1),
        ("M2 · MAKRO-ANALYST", m2),
        ("M3 · RISIKO", m3),
        ("M4 · WALE", m4),
        ("BOT · AUSFÜHRUNG", bot_st),
        ("M5 · HIRN", m5),
    ]
    return [
        {"label": label, "status": st, "description": desc}
        for label, (st, desc) in pairs
    ]


def count_healthy(modules: Iterable[dict]) -> int:
    return sum(1 for m in modules if m["status"] in ("ok", "info"))
