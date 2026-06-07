"""
m5_assistant.py — Börsenhirn AI Assistant (M5)
El cerebro conversacional de la plataforma.

Acceso completo a todos los módulos via FastAPI.
Memoria de largo plazo en Postgres.
Sugiere, evalúa, recomienda y mejora estrategias.

Uso:
    python m5_assistant.py              # chat interactivo en terminal
    python m5_assistant.py --once "tu pregunta"  # una sola consulta
"""

import os, sys, json, logging, argparse
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
import anthropic
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
API_URL        = os.getenv("BOT_API_URL", "http://localhost:8000")
CLAUDE_MODEL   = "claude-sonnet-4-20250514"
MAX_TOKENS     = 2048
HISTORY_LIMIT  = 20          # últimos N mensajes que se mandan como contexto
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:uriel@localhost:5432/borsenhirn")

# ── Database — tabla de conversaciones ───────────────────────────────────────
def get_db():
    return psycopg2.connect(DB_URL)

def ensure_table():
    """Crea la tabla de historial si no existe."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS assistant_history (
                        id          SERIAL PRIMARY KEY,
                        role        VARCHAR(20)  NOT NULL,
                        content     TEXT         NOT NULL,
                        created_at  TIMESTAMPTZ  DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS assistant_suggestions (
                        id          SERIAL PRIMARY KEY,
                        suggestion  TEXT         NOT NULL,
                        context     TEXT,
                        applied     BOOLEAN      DEFAULT FALSE,
                        created_at  TIMESTAMPTZ  DEFAULT NOW()
                    );
                """)
            conn.commit()
        logger.info("Tablas del asistente verificadas.")
    except Exception as e:
        logger.error(f"Error creando tablas: {e}")

def save_message(role: str, content: str):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO assistant_history (role, content) VALUES (%s, %s)",
                    (role, content)
                )
            conn.commit()
    except Exception as e:
        logger.error(f"Error guardando mensaje: {e}")

def load_history(limit: int = HISTORY_LIMIT) -> list:
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT role, content FROM assistant_history
                    ORDER BY created_at DESC LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    except Exception as e:
        logger.error(f"Error cargando historial: {e}")
        return []

def save_suggestion(suggestion: str, context: str = ""):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO assistant_suggestions (suggestion, context) VALUES (%s, %s)",
                    (suggestion, context)
                )
            conn.commit()
    except Exception as e:
        logger.error(f"Error guardando sugerencia: {e}")

# ── Context Builder — recopila datos de todos los módulos ─────────────────────
class ContextBuilder:
    """Recopila el estado completo de Börsenhirn para dárselo al asistente."""

    def __init__(self, api_url: str = API_URL):
        self.api_url = api_url

    def _get(self, endpoint: str, timeout: int = 8) -> dict:
        try:
            r = requests.get(f"{self.api_url}{endpoint}", timeout=timeout)
            return r.json() if r.status_code == 200 else {}
        except:
            return {}

    def build(self) -> str:
        """Construye un bloque de contexto completo en texto."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status  = self._get("/status")
        perf    = self._get("/performance")
        trades  = self._get("/trades?limit=20")
        health  = self._get("/health")

        bot     = status.get("bot", {})
        memory  = status.get("memory", {})
        account = status.get("account", {})
        regime  = status.get("regime", {})

        # Trades recientes
        trades_list = trades if isinstance(trades, list) else []
        recent_sells = [t for t in trades_list if t.get("action") == "sell"][-5:]
        recent_buys  = [t for t in trades_list if t.get("action") == "buy"][-5:]

        # Symbol scores top 5
        sym_scores = perf.get("symbol_scores", {})
        top_symbols = sorted(
            [(k, v) for k, v in sym_scores.items() if v.get("total_trades", 0) > 0],
            key=lambda x: x[1].get("score", 0.5), reverse=True
        )[:5]

        # Régimen
        if isinstance(regime, dict):
            regime_str = regime.get("regime", "—")
            vix_str    = f"{regime.get('vix', 0):.1f}"
            conf_str   = f"{regime.get('confidence', 0):.0%}"
            trend_str  = regime.get("spy_trend", "—")
        else:
            regime_str = str(regime)
            vix_str = conf_str = trend_str = "—"

        # Construir texto de contexto
        ctx_lines = [
            f"=== CONTEXTO BÖRSENHIRN — {now} ===",
            "",
            "── CUENTA ──────────────────────────────",
            f"Equity:         ${account.get('equity', 0):,.2f}",
            f"Buying power:   ${account.get('buying_power', 0):,.2f}",
            f"Cash:           ${account.get('cash', 0):,.2f}",
            f"Modo:           {'LIVE' if bot.get('live_mode') else 'PAPER TRADING'}",
            "",
            "── ACTIVIDAD DE HOY ─────────────────────",
            f"Trades hoy:     {memory.get('trades_today', 0)}",
            f"Wins / Losses:  {memory.get('wins_today', 0)}W / {memory.get('losses_today', 0)}L",
            f"P&L del día:    ${memory.get('daily_pnl', 0):+.2f}",
            "",
            "── MERCADO ──────────────────────────────",
            f"Régimen:        {regime_str} (confianza {conf_str})",
            f"VIX:            {vix_str}",
            f"SPY trend:      {trend_str}",
            "",
            "── PERFORMANCE HISTÓRICO ────────────────",
            f"Total trades:   {perf.get('total_trades', 0)}",
            f"Total wins:     {perf.get('total_wins', 0)}",
            f"Total P&L:      ${perf.get('total_pnl', 0):+.2f}",
            "",
        ]

        # Top symbols
        if top_symbols:
            ctx_lines.append("── TOP SÍMBOLOS (por score histórico) ───")
            for sym, data in top_symbols:
                wr  = data.get("win_rate", 0) * 100
                pnl = data.get("total_pnl", 0)
                ctx_lines.append(
                    f"  {sym:<6} score={data.get('score',0.5):.2f} | "
                    f"wr={wr:.0f}% | pnl=${pnl:+.2f}"
                )
            ctx_lines.append("")

        # Últimos trades
        if recent_buys or recent_sells:
            ctx_lines.append("── ÚLTIMOS TRADES ───────────────────────")
            for t in (recent_buys + recent_sells)[-6:]:
                action = t.get("action","").upper()
                symbol = t.get("symbol","—")
                price  = t.get("price", 0)
                pnl    = t.get("pnl")
                reason = t.get("reason","")[:60]
                pnl_str = f" | pnl=${pnl:+.2f}" if pnl is not None else ""
                ctx_lines.append(f"  {action} {symbol} @ ${price:.2f}{pnl_str} — {reason}")
            ctx_lines.append("")

        # Régimen stats
        regime_stats = perf.get("regime_stats", {})
        if regime_stats:
            ctx_lines.append("── PERFORMANCE POR RÉGIMEN ──────────────")
            for reg, stats in regime_stats.items():
                wr  = stats.get("win_rate", 0) * 100
                pnl = stats.get("total_pnl", 0)
                tot = stats.get("total_trades", 0)
                ctx_lines.append(
                    f"  {reg:<10} {tot} trades | wr={wr:.0f}% | pnl=${pnl:+.2f}"
                )
            ctx_lines.append("")

        ctx_lines.append("=" * 42)
        return "\n".join(ctx_lines)


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Eres el AI Assistant de Börsenhirn, una plataforma de inteligencia financiera end-to-end.

Tu nombre es Hirn (del alemán "cerebro"). Eres el cerebro conversacional de la plataforma.

## Tu identidad
- Eres un asistente financiero especializado, analítico y directo
- Tienes acceso completo al estado de todos los módulos de Börsenhirn en tiempo real
- Conoces el historial completo de trades, performance, y estrategias
- Hablas en español, con terminología técnica precisa cuando corresponde
- Eres honesto sobre la incertidumbre — nunca das certezas falsas sobre el mercado

## Tus capacidades principales

### 1. Análisis y explicación
- Explicar por qué el bot tomó decisiones específicas
- Analizar el performance histórico e identificar patrones
- Evaluar la salud general del portafolio
- Comparar rendimiento por régimen de mercado

### 2. Sugerencias y mejoras de estrategia
- Sugerir ajustes a los parámetros del bot (stop-loss, take-profit, etc.)
- Evaluar si una estrategia de whale tiene sentido dado el contexto actual
- Recomendar qué sectores priorizar según el régimen de mercado
- Identificar símbolos con mejor y peor historial
- Proponer mejoras a los módulos existentes

### 3. Evaluación de ideas
- Si el usuario presenta una idea de trading, la evalúas objetivamente
- Consideras: régimen actual, historial del símbolo, riesgo, capital disponible
- Das un veredicto claro: viable / riesgosa / no recomendada — con razones
- Sugieres cómo mejorar la idea si tiene potencial

### 4. Asistente personal
- Respondes preguntas sobre cualquier aspecto de la plataforma
- Ayudas a interpretar reportes de M1, M2, M3, M4
- Explicas conceptos financieros cuando se necesita
- Recuerdas el contexto de conversaciones anteriores

## Tu estilo
- Directo y conciso — no das vueltas innecesarias
- Analítico — apoyas tus respuestas con datos del contexto
- Honesto — si algo no está funcionando bien, lo dices
- Proactivo — si ves algo importante en los datos, lo mencionas aunque no te pregunten

## Lo que NO haces
- No garantizas rendimientos futuros
- No das consejos de inversión definitivos (el usuario toma las decisiones finales)
- No ignoras el contexto de riesgo
- No exageras ni minimizas los resultados

## Formato de respuesta
- Para análisis complejos: usa secciones claras con encabezados
- Para respuestas simples: texto directo sin markdown innecesario
- Para sugerencias: lista numerada con razonamiento
- Para evaluaciones: veredicto claro primero, luego detalle

Siempre tienes acceso al contexto actualizado de Börsenhirn que se incluye en cada mensaje.
"""


# ── Assistant Agent ───────────────────────────────────────────────────────────
class AssistantAgent:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no configurada en .env")
        self.client  = anthropic.Anthropic(api_key=api_key)
        self.context = ContextBuilder()
        ensure_table()
        logger.info("AssistantAgent (Hirn) iniciado.")

    def _extract_suggestions(self, response_text: str, user_query: str):
        """Detecta y guarda sugerencias del asistente automáticamente."""
        keywords = ["sugiero", "recomiendo", "considera", "podrías", "deberías",
                    "sería útil", "te recomiendo", "una mejora", "optimizar"]
        lower = response_text.lower()
        if any(kw in lower for kw in keywords):
            save_suggestion(
                suggestion=response_text[:500],
                context=user_query[:200]
            )

    def chat(self, user_message: str, include_context: bool = True) -> str:
        """
        Procesa un mensaje del usuario y retorna la respuesta del asistente.
        """
        # 1. Construir contexto actual
        ctx = self.context.build() if include_context else ""

        # 2. Cargar historial de conversación
        history = load_history(HISTORY_LIMIT)

        # 3. Construir mensajes para Claude
        messages = []

        # Agregar historial previo
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Agregar mensaje actual con contexto
        if ctx:
            full_message = f"{user_message}\n\n[CONTEXTO ACTUALIZADO]\n{ctx}"
        else:
            full_message = user_message

        messages.append({"role": "user", "content": full_message})

        # 4. Llamar a Claude
        from circuit_breaker import claude_cb

        if not claude_cb.can_call():
            logger.warning("[M5] Claude API circuit breaker ABIERTO — asistente no disponible")
            assistant_reply = "Asistente no disponible, Claude API caida"
        else:
            try:
                response = self.client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )
                assistant_reply = response.content[0].text
                claude_cb.record_success()

            except (anthropic.APIError, Exception) as e:
                claude_cb.record_failure()
                logger.error(f"Error Claude API: {e}")
                assistant_reply = "Asistente no disponible, Claude API caida"

        # 5. Guardar en historial (guardamos el mensaje limpio sin contexto)
        save_message("user", user_message)
        save_message("assistant", assistant_reply)

        # 6. Detectar y guardar sugerencias
        self._extract_suggestions(assistant_reply, user_message)

        return assistant_reply

    def quick_analysis(self) -> str:
        """Análisis proactivo del estado actual — sin input del usuario."""
        prompt = (
            "Analiza el estado actual de Börsenhirn y dame un resumen ejecutivo. "
            "Incluye: (1) salud del portafolio, (2) algo destacable del performance, "
            "(3) una sugerencia concreta si ves algo que mejorar, "
            "(4) cualquier alerta o punto de atención. "
            "Sé directo y usa los datos del contexto."
        )
        return self.chat(prompt)

    def evaluate_idea(self, idea: str) -> str:
        """Evalúa una idea de trading o estrategia específica."""
        prompt = (
            f"Evalúa esta idea de trading considerando el contexto actual de Börsenhirn:\n\n"
            f"IDEA: {idea}\n\n"
            f"Dame: (1) veredicto claro (viable/riesgosa/no recomendada), "
            f"(2) razones con datos del contexto, "
            f"(3) cómo mejorarla si tiene potencial, "
            f"(4) riesgo estimado dado el capital disponible."
        )
        return self.chat(prompt)

    def suggest_improvements(self) -> str:
        """Genera sugerencias de mejora basadas en el performance actual."""
        prompt = (
            "Basándote en el performance histórico del bot y el contexto actual, "
            "dame 3-5 sugerencias concretas y accionables para mejorar los resultados. "
            "Prioriza las de mayor impacto. Para cada una indica: "
            "qué cambiar, por qué, y qué impacto esperarías."
        )
        return self.chat(prompt)

    def explain_trade(self, symbol: str, action: str = None) -> str:
        """Explica por qué ocurrió un trade específico."""
        action_str = f"de {action.upper()}" if action else ""
        prompt = (
            f"Explica el trade {action_str} de {symbol.upper()} más reciente. "
            f"¿Qué señales lo generaron? ¿Fue una buena decisión dado el contexto? "
            f"¿Qué resultado tuvo?"
        )
        return self.chat(prompt)

    def clear_history(self):
        """Borra el historial de conversación."""
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM assistant_history")
                conn.commit()
            logger.info("Historial borrado.")
            print("\n[Historial de conversación borrado.]\n")
        except Exception as e:
            logger.error(f"Error borrando historial: {e}")


# ── CLI interactivo ───────────────────────────────────────────────────────────
def print_header():
    print("\n" + "═" * 58)
    print("  🧠  BÖRSENHIRN — AI Assistant (Hirn)")
    print("  Tu asistente financiero personal")
    print("═" * 58)
    print("  Comandos especiales:")
    print("    /analisis    → análisis proactivo del portafolio")
    print("    /mejoras     → sugerencias de mejora del bot")
    print("    /idea <text> → evalúa una idea de trading")
    print("    /trade <SYM> → explica el último trade de un símbolo")
    print("    /limpiar     → borrar historial de conversación")
    print("    /salir       → cerrar el asistente")
    print("═" * 58 + "\n")


def run_interactive():
    """Modo chat interactivo en terminal."""
    print_header()

    try:
        agent = AssistantAgent()
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("Agrega ANTHROPIC_API_KEY en tu archivo .env\n")
        return

    # Saludo inicial con análisis rápido
    print("Hirn: Iniciando análisis del estado actual...\n")
    try:
        greeting = agent.quick_analysis()
        print(f"Hirn: {greeting}\n")
    except Exception as e:
        print(f"Hirn: Hola. Listo para ayudarte. (No pude conectar con la API: {e})\n")

    print("─" * 58)

    while True:
        try:
            user_input = input("\nTú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nHirn: Hasta luego.\n")
            break

        if not user_input:
            continue

        # Comandos especiales
        if user_input.lower() in ("/salir", "/exit", "/quit"):
            print("\nHirn: Hasta luego.\n")
            break

        elif user_input.lower() == "/limpiar":
            agent.clear_history()
            continue

        elif user_input.lower() == "/analisis":
            print("\nHirn: Analizando...\n")
            response = agent.quick_analysis()
            print(f"Hirn: {response}")

        elif user_input.lower() == "/mejoras":
            print("\nHirn: Generando sugerencias...\n")
            response = agent.suggest_improvements()
            print(f"Hirn: {response}")

        elif user_input.lower().startswith("/idea "):
            idea = user_input[6:].strip()
            if idea:
                print("\nHirn: Evaluando idea...\n")
                response = agent.evaluate_idea(idea)
                print(f"Hirn: {response}")
            else:
                print("Hirn: Escribe la idea después de /idea")

        elif user_input.lower().startswith("/trade "):
            parts = user_input.split()
            symbol = parts[1] if len(parts) > 1 else ""
            action = parts[2] if len(parts) > 2 else None
            if symbol:
                print(f"\nHirn: Analizando trade de {symbol.upper()}...\n")
                response = agent.explain_trade(symbol, action)
                print(f"Hirn: {response}")
            else:
                print("Hirn: Escribe el símbolo después de /trade (ej: /trade AAPL)")

        else:
            # Conversación normal
            print("\nHirn: Pensando...\n")
            response = agent.chat(user_input)
            print(f"Hirn: {response}")

        print("\n" + "─" * 58)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Börsenhirn AI Assistant")
    p.add_argument("--once",     type=str, help="Una sola consulta y salir")
    p.add_argument("--analisis", action="store_true", help="Análisis rápido del portafolio")
    p.add_argument("--mejoras",  action="store_true", help="Sugerencias de mejora")
    p.add_argument("--idea",     type=str, help="Evalúa una idea de trading")
    a = p.parse_args()

    agent = AssistantAgent()

    if a.once:
        print(agent.chat(a.once))
    elif a.analisis:
        print(agent.quick_analysis())
    elif a.mejoras:
        print(agent.suggest_improvements())
    elif a.idea:
        print(agent.evaluate_idea(a.idea))
    else:
        run_interactive()