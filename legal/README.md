# Legal documents — Börsenhirn

Templates de los tres documentos que cualquier producto de trading
debe tener **antes** de aceptar usuarios externos.

| Archivo | Para qué sirve |
|---|---|
| [`DISCLAIMER.md`](./DISCLAIMER.md) | Texto fuerte "no es asesoría financiera" que va en README, dashboard, landing, footer. |
| [`TERMS.md`](./TERMS.md) | Terms of Service. Responsabilidad, IP, prohibited uses, límite de liability, dispute resolution. |
| [`PRIVACY.md`](./PRIVACY.md) | Privacy Policy. Qué data se recolecta, dónde se guarda, retention, third parties, derechos del usuario. |

---

## ⚠️ Importante

Estos archivos son **plantillas conservadoras** basadas en las
prácticas estándar de la industria. Sirven para:

- Proteger legalmente al proyecto mientras sea de uso personal /
  educativo / self-hosted.
- Darte un piso razonable antes de mostrarlo públicamente en
  GitHub / LinkedIn / portfolio.
- Ser el punto de partida cuando quieras facturar.

**NO SUSTITUYEN asesoría legal real.** Antes de:

1. Abrir inscripciones públicas / beta pública.
2. Aceptar pagos (Stripe / PayPal / cualquier forma).
3. Hacer marketing activo.
4. Dar tu producto a un influencer / bootcamp / clase.

→ Pagá una consulta legal single-shot. Presupuesto típico:
  - En LatAm: 300-800 USD con un abogado local de propiedad
    intelectual / tecnología.
  - En US/EU: 1000-3000 USD con un fintech / securities attorney.

Pedirle específicamente:

- Validar que el lenguaje del Disclaimer te aísla de
  responsabilidad bajo la regulación que aplica (en Colombia: SFC y
  Ley 964 de 2005; en US: Investment Advisers Act of 1940).
- Revisar si tu modelo de SaaS cae en "investment advisor" y
  requiere registro.
- Validar el Privacy contra GDPR (UE), CCPA (California),
  Ley 1581 de 2012 (Colombia).
- Definir jurisdicción y método de arbitraje correctos.

---

## Integración mínima sin abogado

Mientras el proyecto sea **personal / self-hosted / sin usuarios
pagos**, estas acciones son suficientes para reducir riesgo:

1. Banner permanente en el dashboard con el disclaimer corto.
2. Link a `legal/DISCLAIMER.md` en README.md y cada página pública.
3. Auditar el lenguaje: no decir "recomendamos", "vas a ganar",
   "garantizado". Usar: "señal educativa", "histórico muestra…",
   "resultado simulado". Ver `scripts/audit_language.py`.
4. Marcar cada backtest como "simulado" en grandes letras.
5. Evitar nombres que suenen a asesor ("advisor", "wealth manager").
6. No prometer métricas futuras en marketing.

## Qué hacer ANTES del primer usuario externo

Además de lo anterior:

1. Revisión legal contratada.
2. Checkbox de opt-in explícito en signup: "He leído y acepto los
   Terms of Service y Privacy Policy". Log en DB.
3. Versión firmada de los docs (fechas y hash) disponibles
   públicamente.
4. Mecanismo de export / delete de datos del usuario.
5. DPA (Data Processing Agreement) con terceros clave (Anthropic,
   Alpaca) si operás en UE.

## Qué hacer ANTES del primer pago

1. Registrar la marca "Börsenhirn" o el nombre comercial elegido.
2. Incorporar entidad legal (LLC, SAS, limited company) para aislar
   responsabilidad personal.
3. Seguro de responsabilidad civil profesional (errors & omissions).
4. Compliance con PCI-DSS si tocás tarjetas (normalmente lo cubre
   Stripe).
5. Revisión final de toda documentación legal por abogado.
6. Registro fiscal (IVA / sales tax) donde aplique.

---

**Last updated:** 2026-04-24.
