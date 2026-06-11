# Always-on (Opción C) — Börsenhirn bot como servicio

Meta: que el bot corra **solo**, sin terminal abierta, arrancando al boot y
reiniciándose si crashea. Sigue siendo **PAPER** (sin `--live`), contra
`borsenhirn_dev`. Cero riesgo de plata real.

Hay dos niveles. Empezá por **C1**; pasá a **C2** solo si querés 24/7 real
independiente de tu laptop.

---

## C1 — Servicio systemd en tu WSL (hacelo hoy)

Tu WSL ya tiene systemd activo (`systemd=true`). El unit ya está en el repo:
`scripts/borsenhirn-bot.service`.

### Instalar (una sola vez) — corré esto en tu terminal WSL:

```bash
cd /home/casta/proyecto_trading

# 1) Copiar el unit a systemd (pide sudo)
sudo cp scripts/borsenhirn-bot.service /etc/systemd/system/borsenhirn-bot.service

# 2) Recargar systemd y habilitar arranque automático al boot
sudo systemctl daemon-reload
sudo systemctl enable borsenhirn-bot.service

# 3) Arrancarlo ahora
sudo systemctl start borsenhirn-bot.service

# 4) Ver que quedó corriendo
systemctl status borsenhirn-bot.service --no-pager
```

Si el `status` muestra **active (running)** → listo, el bot ya corre solo.
(Ahora mismo el mercado está cerrado, así que va a loggear "Mercado cerrado —
esperando apertura" y dormir. Eso es lo correcto.)

### Manejo diario

```bash
# Ver el bot en vivo
tail -f /home/casta/proyecto_trading/logs/bot_service.log
# o por journald:
journalctl -u borsenhirn-bot.service -f

systemctl status borsenhirn-bot.service     # ¿corriendo? ¿cuándo arrancó?
sudo systemctl restart borsenhirn-bot.service  # reiniciar (p.ej. tras git pull)
sudo systemctl stop borsenhirn-bot.service     # PAUSAR (tu rutina del sábado)
sudo systemctl start borsenhirn-bot.service    # reanudar
```

### Pausa de los sábados
Tu plan es pausar el sábado para revisar. Con el servicio:
```bash
sudo systemctl stop borsenhirn-bot.service     # sábado: pausa
# ...revisás performance...
sudo systemctl start borsenhirn-bot.service    # lunes: reanuda
```
El bot igual se auto-gatea por horario de mercado, así que dejarlo prendido el
finde tampoco tradea — pero parar/arrancar te da control explícito.

### El matiz honesto de WSL
El servicio corre **mientras Windows + WSL estén prendidos**. WSL se apaga si:
- apagás/reiniciás la PC, o
- Windows entra en suspensión/hibernación, o
- WSL se cierra por inactividad.

Mitigaciones:
- **Que la PC no duerma** en horario de mercado (Configuración de energía de
  Windows → Suspensión = Nunca, al menos enchufada).
- Evitar que WSL se apague solo: en Windows, archivo `%UserProfile%\.wslconfig`
  con:
  ```ini
  [experimental]
  autoMemoryReclaim=disabled
  ```
  y mantener al menos una ventana WSL abierta ayuda. Aun así, si la PC se apaga,
  el bot no corre.

> Si tu laptop **no** está prendida de 9:30 a 16:00 ET todos los días hábiles,
> C1 va a perder trades. Para eso está C2.

---

## C2 — VPS 24/7 (independiente de tu PC)

Lo robusto de verdad: una maquinita en la nube siempre prendida. ~$5/mes
(Hetzner, DigitalOcean, Linode, Fly.io). **El mismo unit file funciona igual.**

### Pasos (resumen)
1. Crear un VPS Ubuntu 24.04 (1 vCPU / 1-2 GB alcanza).
2. Instalar deps: `sudo apt update && sudo apt install -y python3-venv git postgresql`.
3. Clonar el repo (deploy key de solo lectura) y crear el `venv`:
   ```bash
   git clone git@github.com:Obumbratio/proyecto_trading.git
   cd proyecto_trading
   python3 -m venv venv && venv/bin/pip install -r requirements.txt
   ```
4. **Base de datos:** crear `borsenhirn_dev` en el postgres del VPS y correr las
   migraciones (mismo esquema que local). NO uses la DB de prod.
5. Copiar tu `.env` (paper) al VPS — Alpaca paper keys + creds de la DB local
   del VPS. **Nunca** subas `.env` a git.
6. Ajustar rutas en el unit si el usuario/ruta cambian (p.ej. `User=ubuntu`,
   `WorkingDirectory=/home/ubuntu/proyecto_trading`), y luego los mismos pasos
   de instalación de C1 (`cp` → `daemon-reload` → `enable` → `start`).

### Ventajas
- Corre 24/7 sin importar tu laptop.
- No se pierde ningún día de mercado.
- Lo monitoreás por Discord (alertas) y, si querés el dashboard, lo levantás
  apuntando a la API del VPS o por SSH túnel.

### Ojo
- Sigue siendo paper hasta que vos decidas pasar a live (otro tema, otro día).
- Un VPS es una superficie expuesta: SSH con clave (no password), firewall,
  no abrir el puerto de la API/dashboard a internet (usá SSH túnel).

---

## Pase de anomalías por tenant (timer horario)

Independiente del bot: un **systemd timer** corre el detector de anomalías (B10)
sobre todos los tenants ACTIVE **cada hora** (`scripts/run_anomaly_scan.py` vía
`scan_anomalies_all_tenants`). Solo alerta (no bloquea) y rutea a la `alert_mgr`
de cada tenant. Funciona igual en C1 (WSL) y C2 (VPS). Units en el repo:
`scripts/borsenhirn-anomaly.service` (oneshot) + `scripts/borsenhirn-anomaly.timer`.

### Instalar (una sola vez) — en la terminal del host:

```bash
cd /home/casta/proyecto_trading

# 1) Copiar service + timer a systemd
sudo cp scripts/borsenhirn-anomaly.service /etc/systemd/system/
sudo cp scripts/borsenhirn-anomaly.timer   /etc/systemd/system/

# 2) Recargar y habilitar el TIMER (no el service: el timer lo dispara)
sudo systemctl daemon-reload
sudo systemctl enable --now borsenhirn-anomaly.timer

# 3) Verificar que quedó agendado
systemctl status borsenhirn-anomaly.timer --no-pager
systemctl list-timers borsenhirn-anomaly.timer --no-pager   # próxima corrida
```

### Manejo / verificación

```bash
# Forzar un pase ahora (sin esperar la hora)
sudo systemctl start borsenhirn-anomaly.service
# Ver el resultado del último pase
tail -n 20 /home/casta/proyecto_trading/logs/anomaly_scan.log
journalctl -u borsenhirn-anomaly.service -n 50 --no-pager
# Deshabilitar el agendado
sudo systemctl disable --now borsenhirn-anomaly.timer
```

> Probado a mano: `venv/bin/python -m scripts.run_anomaly_scan` → un pase y sale 0.
> Cadencia horaria + dedupe del AlertManager evitan re-alertar lo mismo sin parar.
> En el VPS (C2) ajustá `User=`/`WorkingDirectory=` en el `.service` igual que el bot.

---

## Pasar a plata real (NO ahora)
Cuando algún día quieras live: cuenta Alpaca live + `LIVE_ALPACA_*` en `.env` y
cambiar el `ExecStart` del unit a `... main.py --live`. Con mucho cuidado y
después de meses de paper convincente. Hoy no toca.

---

## Resumen de decisión
| | C1 (WSL) | C2 (VPS) |
|---|---|---|
| Costo | $0 | ~$5/mes |
| Setup | 4 comandos | ~30 min |
| Corre 24/7 | solo con PC prendida | sí, siempre |
| Pierde trades si dormís la PC | sí | no |

**Recomendación:** arrancá con **C1 hoy** (es gratis y ya tenés todo). Si en un
par de semanas ves que tu PC no está siempre prendida en horario de mercado,
mové a **C2**.
