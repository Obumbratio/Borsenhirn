import { Panel, PanelBody } from "@/components/ui/Panel";

export const dynamic = "force-dynamic";

type Message = {
  id: string;
  sender: "user" | "hirn";
  text: string;
  timestamp: string;
};

const CHAT_HISTORY: Message[] = [
  {
    id: "m1",
    sender: "user",
    text: "¿Debería comprar Nvidia (NVDA) ahora que tiene un score de 0.72?",
    timestamp: "Hace unos minutos",
  },
  {
    id: "m2",
    sender: "hirn",
    text: "Como asistente de inteligencia financiera impersonal, no puedo dar recomendaciones personalizadas ni decirte si deberías comprar o vender un activo específico. Esa decisión depende de tus reglas de trading y capital.\n\nTe sugiero revisar el setup de NVDA en el Tablero y abrir la **Calculadora de Posición** para ingresar tu capital y porcentaje de riesgo. La calculadora computará el tamaño exacto de tu lote y los escenarios posibles en base a los niveles técnicos de entrada y stop sugeridos. Si quieres, puedo explicarte qué factores técnicos sustentan ese score de 0.72 o cómo interpretar el nivel del stop loss.",
    timestamp: "Hace unos minutos",
  },
  {
    id: "m3",
    sender: "user",
    text: "Explicame qué es el RSI(14) y qué significa que esté en 58.3 en este análisis.",
    timestamp: "Hace un momento",
  },
  {
    id: "m4",
    sender: "hirn",
    text: "El RSI (Relative Strength Index) es un oscilador de impulso que mide la velocidad y el cambio de los movimientos de precio en una escala de 0 a 100.\n\n* Un valor de **58.3** indica un impulso moderadamente alcista. No está sobrecomprado (generalmente >70) ni sobrevendido (<30), lo que sugiere que el precio tiene espacio para seguir subiendo dentro de la tendencia actual sin estar recalentado.\n* En el modelo determinista de Börsenhirn, el valor del RSI(14) se combina con el régimen macro del mercado para ponderar el score general del setup. En este caso, al no haber sobrecompra extrema, se considera un factor de soporte constructivo para una posición LONG.",
    timestamp: "Recién",
  },
];

export default function HirnPage() {
  return (
    <div className="mx-auto flex max-w-[800px] flex-col gap-3">
      <header className="px-1 pt-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-fraunces text-[22px] font-semibold text-wht">Hirn Asistente</h1>
          <span className="rounded-full bg-ac/15 px-2.5 py-0.5 text-xs font-semibold text-ac border border-ac/20">
            MAQUETA DEMO
          </span>
        </div>
        <p className="mt-0.5 text-[13px] text-dim">
          Asistente educativo e impersonal. Explica conceptos y procedencias; nunca aconseja operar.
        </p>
      </header>

      {/* Exención regulatoria visible / Disclaimer */}
      <div className="rounded-lg border border-warn/25 bg-warn/5 px-4 py-3 text-xs leading-relaxed text-warn">
        <span className="font-semibold">Línea Roja Legal:</span> Hirn es una herramienta exclusivamente
        educativa e impersonal. No conoce tu saldo, no ve tu cartera y bajo ninguna circunstancia
        generará recomendaciones de inversión dirigidas a ti. Si tienes dudas sobre una operación,
        usa la calculadora de posición.
      </div>

      {/* Historial de Chat */}
      <div className="mt-2 flex flex-col gap-4 rounded-xl border border-bd bg-pan/20 p-4">
        {CHAT_HISTORY.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col max-w-[85%] ${
              msg.sender === "user" ? "ml-auto items-end" : "mr-auto items-start"
            }`}
          >
            <span className="text-[10px] text-dim2 mb-1 px-1">{msg.sender === "user" ? "Tú" : "Börsenhirn"}</span>
            <div
              className={`rounded-xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-line ${
                msg.sender === "user"
                  ? "bg-ac2 text-wht rounded-tr-none"
                  : "bg-pan border border-bd text-tx rounded-tl-none"
              }`}
            >
              {msg.text}
            </div>
            <span className="text-[9px] text-dim2 mt-1 px-1">{msg.timestamp}</span>
          </div>
        ))}
      </div>

      {/* Input de Chat mockeado */}
      <Panel>
        <PanelBody className="flex gap-2">
          <input
            type="text"
            disabled
            placeholder="Preguntame sobre indicadores o conceptos del tablero (chat deshabilitado en maqueta)..."
            className="flex-1 rounded-md border border-bd bg-pan2 px-3 py-2 text-sm text-dim2 outline-none cursor-not-allowed"
          />
          <button
            disabled
            className="rounded-md bg-ac2/50 px-4 py-2 text-sm font-semibold text-wht/50 cursor-not-allowed"
          >
            Enviar
          </button>
        </PanelBody>
      </Panel>
    </div>
  );
}
