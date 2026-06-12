# Börsenhirn — Plan de producto y go-to-market
### Modelo: herramienta de inteligencia + IA explicativa (BYO broker, paper-first, el usuario ejecuta)

> Documento guía. Resume el camino elegido, los pasos por fase, los pros/contras, y las trampas a evitar.

---

## 0. La regla de oro (no la rompas)

Todo el modelo se sostiene sobre una línea: **tu producto da información y herramientas impersonales; el usuario decide y ejecuta.** Mientras te mantengas de ese lado, no necesitas registrarte como asesor de inversión.

Cruzas la línea (y te conviertes en asesor registrado / robo-advisor) si:
- Das recomendaciones **personalizadas** al perfil/capital/cuenta de un usuario específico.
- Ejecutas trades de forma **discrecional** (sin que el usuario apruebe cada uno).
- Cobras **% de AUM** o **comisión sobre ganancias**.

Te quedas del lado seguro si:
- El análisis/señales son **iguales para todos** (impersonales).
- El "cuánto comprar" es una **calculadora que el usuario opera**, no un consejo a medida.
- El usuario **aprieta el botón** de cada orden.
- Cobras **suscripción fija**.
- Empiezas en **paper trading** por defecto.

---

## 1. Qué hace el producto (y qué NO hace)

Dos piezas separadas a propósito. **Nunca conectes las dos en un "para ti, compra esto".**

### Pieza 1 — El análisis (impersonal: igual para todos)
La IA publica el análisis de una empresa como información general, idéntica para cualquier usuario. Tarjeta de análisis: tesis + nivel de entrada/stop/objetivo de referencia + qué invalida la tesis. La IA explica el *porqué*, no solo escupe una señal.

### Pieza 2 — La calculadora (la opera el usuario con SUS números)
El usuario mete su capital y su % de riesgo; toma los niveles del análisis (editables); la herramienta hace aritmética: riesgo en $, acciones que encajan, costo, escenario de stop/objetivo, relación riesgo/beneficio. El tamaño sale de **la regla del propio usuario**, no de una opinión nuestra. Escenarios neutrales, no un empujón a actuar.

### El botón (la ejecución es del usuario)
El usuario decide y aprieta comprar; la orden va a *su* cuenta de Alpaca. Nunca ejecutamos por él ni tocamos su dinero. Siempre visible: *"herramienta de cálculo, tú eliges y ejecutas, no es recomendación de inversión."*

### SÍ hace / NO hace
**SÍ:** research/resúmenes; análisis impersonal + el porqué; tarjetas con niveles; calculadora operada por el user; escenarios y R/B; paper por defecto; track record público honesto; conexión a Alpaca para que el user apruebe/ejecute cada orden.
**NO (líneas rojas):** no "para tu cuenta de $X compra Y"; no decide cuánto arriesgar; no ejecuta auto/discrecional; no custodia dinero; no promete retornos (AI-washing); no cobra sobre AUM/performance.

---

## 2. Plan por fases (resumen)
- **Fase 0** — LLC + ToS/disclaimers + presupuestar opinión legal (~2–5k USD) antes de cobrar/abrir a usuarios.
- **Fase 1** — Slice vertical web: login (Clerk) → aceptar legal → conectar Alpaca (paper) → ver análisis/señales → calculadora → botón comprar (paper).
- **Fase 2** — IA explicativa (tesis/riesgo/qué invalida) + track record público honesto + research on-demand.
- **Fase 3** — Beta privada 5–10 usuarios en paper; medir **retención** (churn brutal en la categoría).
- **Fase 4** — Despliegue real (VPS 5–10 USD/mes; local-first no deja entrar a nadie de afuera); secrets live, dominio, HTTPS.
- **Fase 5** — Monetización: **suscripción fija** (USD 20–40/mes), freemium (paper gratis). Nunca AUM/performance.
- **Fase 6** — Escalar: más brokers; evaluar RIA para personalización; expansión (UE/CNMV línea más estrecha; Latam país por país).

---

## 3. Dónde estaba la idea equivocada (corregido)
1. "Sugerencias según el capital del usuario" → consejo personalizado = robo-advisor. **Corrección:** análisis impersonal + calculadora operada por el user.
2. "El botón me cubre de todo" → cubre custodia/ejecución, NO personalización. Ejes distintos.
3. Presentar la IA como más de lo que es → AI-washing, foco SEC. Solo lo que hace de verdad + track record.
4. "El reto es técnico" → el backend ya está; el reto real es **conseguir y retener usuarios** (distribución).

---

## 4. Pros/contras (honesto)
**A favor:** backend ya construido (ventaja de meses); diferenciador real (IA explicativa + transparencia); mercado creciendo; costos bajos local-first.
**En contra:** espacio poblado (TradersPost, Danelfin, Composer, Tickeron, Intellectia…); confianza difícil; valor difícil de demostrar; churn alto; gasto legal + disciplina para no cruzar la línea; fundador solo (banda limitada en marketing).

## 5. Diferenciación (el hueco)
IA que explica + transparencia verificable + UX para el que no programa + BYO broker + paper-first, sin cruzar a discreción/personalización. Posición: "el lugar donde el retail entiende y prueba antes de arriesgar", no "el bot que te hace rico".

## 6. Próximos pasos accionables
1. LLC + ToS/disclaimers + presupuestar opinión legal.
2. Node + app Clerk + `AUTH_VERIFIER=clerk`.
3. Slice vertical: login → legal → conectar Alpaca paper → señales → calculadora → botón comprar.
4. IA explicativa + track record público.
5. Beta 5–10 usuarios en paper; medir retención.
6. VPS barato; secrets live.
7. Suscripción fija; primer cobro.
8. Escalar / RIA / expansión.

---

*Recordatorio: esto no es asesoría legal. La frontera impersonal-vs-personalizado depende del diseño final; confírmalo con un abogado de securities antes de abrir a usuarios reales o cobrar.*
