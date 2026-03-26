"""
my_plan.py - Sistema de planes personalizados de trading.

El usuario describe su idea en lenguaje natural.
La IA la convierte en reglas ejecutables concretas.
El bot corre el plan en paralelo con la estrategia segura (SPY).

Uso directo:
    python my_plan.py              # wizard para crear/ver plan
    python my_plan.py --status     # ver plan activo
    python my_plan.py --clear      # borrar plan activo
"""

import os, json, logging, argparse, requests
from datetime import datetime, timezone, timedelta

import config
from logger import setup_logging
from data_fetcher import DataFetcher
from indicators import add_all_indicators
from ml_model import TradingModel

logger = logging.getLogger(__name__)

PLAN_FILE = "reports/mi_plan_activo.json"
os.makedirs("reports", exist_ok=True)


# ══════════════════════════════════════════════════════════════
# CLAUDE API
# ══════════════════════════════════════════════════════════════
def _claude(prompt: str, system: str) -> str:
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        data = resp.json()
        if "content" not in data:
            return f"[Error API: {data.get('error',{}).get('message', str(data))}]"
        return data["content"][0]["text"]
    except Exception as e:
        return f"[Error IA: {e}]"


# ══════════════════════════════════════════════════════════════
# GUARDAR / CARGAR PLAN
# ══════════════════════════════════════════════════════════════
def save_plan(plan: dict):
    with open(PLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def load_plan() -> dict:
    if os.path.exists(PLAN_FILE):
        with open(PLAN_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def clear_plan():
    if os.path.exists(PLAN_FILE):
        os.remove(PLAN_FILE)
        print("\n  Plan borrado.")
    else:
        print("\n  No hay plan activo.")


# ══════════════════════════════════════════════════════════════
# WIZARD — CREAR PLAN CON IA
# ══════════════════════════════════════════════════════════════
def create_plan_wizard():
    print(f"\n{'═'*58}")
    print(f"  CREAR MI PLAN DE TRADING")
    print(f"{'═'*58}")
    print("\n  Describe tu idea de trading en lenguaje natural.")
    print("  Ejemplos:")
    print("    'quiero comprar QQQ cuando caiga mucho tech'")
    print("    'operar GLD cuando el mercado este inestable'")
    print("    'comprar AAPL en caidas fuertes y vender rapido'")
    print("    'quiero algo mas agresivo con semiconductores'")
    print(f"\n{'─'*58}")

    idea = input("\n  Tu idea: ").strip()
    if not idea:
        print("  Cancelado.")
        return

    capital_pct = ""
    while capital_pct not in [str(i) for i in range(10, 55, 5)]:
        print("\n  ¿Cuánto % del capital destinar a este plan?")
        print("  (el resto va a la estrategia segura SPY)")
        print("  Opciones: 10, 15, 20, 25, 30, 35, 40, 50")
        capital_pct = input("  % del capital (recomendado 20-30): ").strip()
        if capital_pct not in [str(i) for i in range(10, 55, 5)]:
            print("  Ingresa un valor valido (10, 15, 20, 25, 30...)")

    capital_pct = int(capital_pct)

    print(f"\n  Analizando tu idea con IA...")

    system = """
Eres un experto en trading algoritmico. El usuario te describe una idea de trading en lenguaje natural.
Tu tarea es convertirla en parametros ejecutables concretos para un bot de trading.

ACTIVOS DISPONIBLES (solo estos, son los soportados por Alpaca paper trading con IEX feed):
ETFs liquidos: SPY, QQQ, IWM, DIA, GLD, SLV, TLT, IEF, VXX, SQQQ, TQQQ, UVXY
Acciones grandes: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD, INTC, JPM, BAC, XOM

TIPOS DE ESTRATEGIA disponibles:
- "momentum": compra cuando el activo sube fuerte, vende cuando pierde momentum
- "mean_reversion": compra en caidas fuertes (RSI bajo), vende en recuperacion (RSI alto)
- "breakout": compra cuando el precio rompe maximos recientes
- "ml_only": usa solo el modelo ML para decidir (mas conservador)
- "hybrid": combinacion de señales tecnicas + ML (por defecto)

RESPONDE SOLO con un JSON valido, sin texto adicional, sin markdown, sin explicaciones:
{
  "symbol": "SIMBOLO",
  "strategy_type": "hybrid|momentum|mean_reversion|breakout|ml_only",
  "idea_original": "lo que dijo el usuario",
  "idea_refinada": "descripcion clara de como funciona la estrategia (2-3 oraciones)",
  "razonamiento": "por que esta estrategia encaja con la idea del usuario",
  "rsi_buy": numero entre 25 y 45,
  "rsi_sell": numero entre 55 y 80,
  "ml_threshold_buy": numero entre 0.45 y 0.70,
  "ml_threshold_sell": numero entre 0.65 and 0.85,
  "stop_loss_pct": numero entre 0.03 y 0.10,
  "take_profit_pct": numero entre 0.05 y 0.25,
  "riesgo": "bajo|medio|alto",
  "advertencias": ["lista", "de", "riesgos"]
}
"""

    raw = _claude(idea, system)

    # Extraer JSON de la respuesta
    plan_params = None
    try:
        # Buscar el JSON en la respuesta
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            plan_params = json.loads(raw[start:end])
    except Exception:
        pass

    if not plan_params:
        print("\n  Error al procesar la respuesta de IA. Intenta de nuevo.")
        print(f"  Respuesta recibida: {raw[:200]}")
        return

    # Mostrar el plan refinado al usuario
    print(f"\n{'═'*58}")
    print(f"  PLAN REFINADO POR IA")
    print(f"{'═'*58}")
    print(f"\n  Tu idea:     {plan_params.get('idea_original', idea)}")
    print(f"\n  Plan:        {plan_params.get('idea_refinada', '')}")
    print(f"\n  Activo:      {plan_params.get('symbol', 'N/A')}")
    print(f"  Estrategia:  {plan_params.get('strategy_type', 'hybrid')}")
    print(f"  Riesgo:      {plan_params.get('riesgo', 'medio').upper()}")
    print(f"\n  Parametros:")
    print(f"    RSI compra:      < {plan_params.get('rsi_buy', 35)}")
    print(f"    RSI venta:       > {plan_params.get('rsi_sell', 65)}")
    print(f"    ML umbral buy:   > {plan_params.get('ml_threshold_buy', 0.55):.0%}")
    print(f"    Stop-loss:       {plan_params.get('stop_loss_pct', 0.05):.0%} desde entrada")
    print(f"    Take-profit:     {plan_params.get('take_profit_pct', 0.10):.0%} desde entrada")
    print(f"    Capital del plan:{capital_pct}%")
    print(f"    Capital seguro:  {100 - capital_pct}% (SPY estrategia base)")

    if plan_params.get("advertencias"):
        print(f"\n  Advertencias:")
        for w in plan_params["advertencias"]:
            print(f"    ! {w}")

    print(f"\n  Razonamiento: {plan_params.get('razonamiento', '')}")
    print(f"\n{'─'*58}")

    confirmar = input("\n  ¿Activar este plan? (s/n): ").strip().lower()
    if confirmar not in ("s", "si", "sí", "y", "yes"):
        print("  Cancelado. El plan no fue guardado.")
        return

    # Guardar plan completo
    plan_params["capital_pct"] = capital_pct / 100.0
    plan_params["safe_capital_pct"] = (100 - capital_pct) / 100.0
    plan_params["activo"] = True
    plan_params["creado"] = datetime.now().isoformat()
    plan_params["entry_price"] = None
    plan_params["shares_held"] = 0

    save_plan(plan_params)
    print(f"\n  Plan activado. El bot ahora opera en modo DUAL:")
    print(f"    {100-capital_pct}% capital -> Estrategia segura (SPY)")
    print(f"    {capital_pct}% capital  -> Tu plan ({plan_params['symbol']})")
    print(f"\n  Arranca el bot con la opcion 1 del menu para que entre en efecto.")


# ══════════════════════════════════════════════════════════════
# MOSTRAR PLAN ACTIVO
# ══════════════════════════════════════════════════════════════
def show_plan():
    plan = load_plan()
    if not plan:
        print("\n  No hay ningun plan activo.")
        print("  Usa la opcion 14 del menu para crear uno.")
        return

    print(f"\n{'═'*58}")
    print(f"  MI PLAN ACTIVO")
    print(f"{'═'*58}")
    print(f"\n  Activo:      {plan.get('symbol')}")
    print(f"  Estrategia:  {plan.get('strategy_type')}")
    print(f"  Idea:        {plan.get('idea_refinada', '')[:80]}")
    print(f"  Riesgo:      {plan.get('riesgo', '?').upper()}")
    print(f"  Capital plan:{plan.get('capital_pct', 0.3)*100:.0f}%")
    print(f"  Capital safe:{plan.get('safe_capital_pct', 0.7)*100:.0f}% (SPY)")
    print(f"  Creado:      {plan.get('creado', 'N/A')[:10]}")
    print(f"\n  Parametros:")
    print(f"    RSI compra:   < {plan.get('rsi_buy', 35)}")
    print(f"    RSI venta:    > {plan.get('rsi_sell', 65)}")
    print(f"    Stop-loss:    {plan.get('stop_loss_pct', 0.05):.0%}")
    print(f"    Take-profit:  {plan.get('take_profit_pct', 0.10):.0%}")

    entry = plan.get("entry_price")
    shares = plan.get("shares_held", 0)
    if entry and shares > 0:
        print(f"\n  Posicion abierta:")
        print(f"    Entrada: ${entry:.2f}  |  Cantidad: {shares}")


# ══════════════════════════════════════════════════════════════
# ESTRATEGIA DEL PLAN (usada por dual_run en main.py)
# ══════════════════════════════════════════════════════════════
class PlanStrategy:
    """Ejecuta la estrategia definida por el usuario en su plan."""

    def __init__(self, plan: dict, model: TradingModel = None):
        self.plan   = plan
        self.model  = model
        self.symbol = plan.get("symbol", "QQQ")
        self.stype  = plan.get("strategy_type", "hybrid")

    def generate_signal(self, df) -> dict:
        result = {"action": "hold", "confidence": 0.0,
                  "stop_loss": 0.0, "reason": "Sin señal."}
        if len(df) < 30:
            result["reason"] = "Datos insuficientes."
            return result
        try:
            last  = df.iloc[-1]
            prev  = df.iloc[-2]
            price = float(last["close"])
            rsi   = float(last.get("rsi", 50))
            atr   = float(last.get("atr", price * 0.01))

            rsi_buy  = self.plan.get("rsi_buy", 35)
            rsi_sell = self.plan.get("rsi_sell", 65)
            sl_pct   = self.plan.get("stop_loss_pct", 0.05)
            tp_pct   = self.plan.get("take_profit_pct", 0.10)
            ml_buy_t = self.plan.get("ml_threshold_buy", 0.55)
            ml_sel_t = self.plan.get("ml_threshold_sell", 0.75)

            # Stop-loss dinamico
            result["stop_loss"] = round(price * (1 - sl_pct), 4)

            # ML
            p_up   = self.model.predict_prob(df) if self.model else 0.5
            p_down = 1.0 - p_up
            ml_buy  = p_up   > ml_buy_t
            ml_sell = p_down > ml_sel_t

            # SMA
            sma_cols = [c for c in df.columns if c.startswith("sma_")]
            uptrend = downtrend = False
            if sma_cols:
                sma_val = float(df[sma_cols[-1]].iloc[-1])  # SMA mas larga disponible
                uptrend   = price > sma_val
                downtrend = price < sma_val

            # RSI
            oversold   = rsi < rsi_buy
            overbought = rsi > rsi_sell
            rsi_rising = rsi > float(prev.get("rsi", 50))
            rsi_falling = rsi < float(prev.get("rsi", 50))

            # BB
            bbl_col = next((c for c in df.columns if c.startswith("BBL")), None)
            bbu_col = next((c for c in df.columns if c.startswith("BBU")), None)
            near_low = bbl_col and price <= float(df[bbl_col].iloc[-1]) * 1.01
            near_hi  = bbu_col and price >= float(df[bbu_col].iloc[-1]) * 0.99

            # MACD
            macd_col = next((c for c in df.columns if "MACD_" in c and "s" not in c.lower() and "h" not in c.lower()), None)
            macds_col = next((c for c in df.columns if "MACDs" in c), None)
            macd_bull = macd_bear = False
            if macd_col and macds_col:
                m, ms = float(df[macd_col].iloc[-1]), float(df[macds_col].iloc[-1])
                mp, msp = float(df[macd_col].iloc[-2]), float(df[macds_col].iloc[-2])
                macd_bull = m > ms and mp <= msp
                macd_bear = m < ms and mp >= msp

            # ── Señales segun tipo de estrategia ──────────────
            buy_reasons  = []
            sell_reasons = []

            if self.stype == "mean_reversion":
                if oversold and rsi_rising:
                    buy_reasons.append(f"RSI={rsi:.0f} sobreventa+subiendo")
                if near_low and ml_buy:
                    buy_reasons.append("Rebote BB inferior + ML")
                if overbought or (near_hi and rsi_falling):
                    sell_reasons.append("RSI sobrecompra / BB superior")

            elif self.stype == "momentum":
                if uptrend and macd_bull and ml_buy:
                    buy_reasons.append("Momentum alcista + MACD + ML")
                if uptrend and rsi_rising and rsi > 50 and ml_buy:
                    buy_reasons.append("Momentum RSI + tendencia")
                if downtrend or macd_bear:
                    sell_reasons.append("Momentum perdido")

            elif self.stype == "breakout":
                recent_high = float(df["high"].iloc[-20:].max())
                if price >= recent_high * 0.995 and ml_buy:
                    buy_reasons.append(f"Breakout maximo {recent_high:.2f}")
                if downtrend and ml_sell:
                    sell_reasons.append("Ruptura bajista")

            elif self.stype == "ml_only":
                if ml_buy:
                    buy_reasons.append(f"ML={p_up:.2f}")
                if ml_sell:
                    sell_reasons.append(f"ML bajista={p_down:.2f}")

            else:  # hybrid (default)
                if oversold and (uptrend or rsi_rising) and ml_buy:
                    buy_reasons.append(f"RSI={rsi:.0f}+tendencia+ML")
                if near_low and rsi_rising and ml_buy:
                    buy_reasons.append("Rebote BB+ML")
                if macd_bull and ml_buy:
                    buy_reasons.append("MACD alcista+ML")
                if uptrend and oversold:
                    buy_reasons.append("Tendencia+RSI bajo")
                if overbought or ml_sell:
                    sell_reasons.append("Sobrecompra/ML venta")
                if macd_bear and downtrend:
                    sell_reasons.append("MACD bajista")

            # Stop-loss y take-profit desde entrada
            entry_price = self.plan.get("entry_price")
            if entry_price and self.plan.get("shares_held", 0) > 0:
                sl_price = entry_price * (1 - sl_pct)
                tp_price = entry_price * (1 + tp_pct)
                if price <= sl_price:
                    sell_reasons.insert(0, f"Stop-loss {sl_pct:.0%}")
                if price >= tp_price:
                    sell_reasons.insert(0, f"Take-profit {tp_pct:.0%}")

            # ── Decision final ─────────────────────────────────
            if buy_reasons and not sell_reasons:
                result.update(action="buy", confidence=round(p_up, 3),
                              reason=" | ".join(buy_reasons))
            elif sell_reasons:
                result.update(action="sell", confidence=round(p_down, 3),
                              reason=" | ".join(sell_reasons))
            else:
                result["reason"] = (f"HOLD | RSI={rsi:.1f} | "
                                    f"{'Tendencia alcista' if uptrend else 'Sin tendencia'} | "
                                    f"ML={p_up:.2f}")
                result["confidence"] = round(p_up, 3)

        except Exception as e:
            logger.error(f"PlanStrategy error: {e}", exc_info=True)
        return result


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    setup_logging()
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true", help="Ver plan activo")
    p.add_argument("--clear",  action="store_true", help="Borrar plan activo")
    a = p.parse_args()

    if a.status:
        show_plan()
    elif a.clear:
        clear_plan()
    else:
        create_plan_wizard()
