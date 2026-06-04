# Plantilla `.env.dev` para la Nitro
> Solo placeholders. NUNCA pongas llaves reales en este archivo (viaja por git).
> En la Nitro: copia el bloque a un archivo `.env.dev`, rellénalo a mano, y
> recuerda que `.env.dev` está en `.gitignore` (no se sube).

## Pasos
1. En la Nitro, dentro del repo:
   ```bash
   # crea el .env.dev (queda ignorado por git, está bien)
   nano .env.dev
   ```
2. Pega el bloque de abajo y reemplaza cada `xxxxx` por el valor real.
3. `DB_HOST` lo sacas con:  `ip route show default | awk '{print $3}'`
   (o `localhost` si tu WSL2 está en modo mirrored).
4. `APP_DB_PASSWORD` debe ser la MISMA password del rol `borsenhirn_app`
   que recreaste en el paso N3 (no la cambies).

## Bloque a copiar
```dotenv
# --- Base de datos (cambia por máquina) ---
DB_HOST=xxxxx          # IP del host Windows desde WSL2, o localhost si mirrored
DB_PORT=5432
DB_NAME=borsenhirn_dev
DB_USER=postgres
DB_PASS=xxxxx          # password admin de Postgres en la Nitro
APP_DB_USER=borsenhirn_app
APP_DB_PASSWORD=xxxxx  # MISMA password del rol recreado en N3

# DATABASE_URL derivada (ajústala a tu forma de conexión)
DATABASE_URL=postgresql://borsenhirn_app:xxxxx@xxxxx:5432/borsenhirn_dev

# --- Llaves de la app (las mismas de tu .env.dev actual) ---
ANTHROPIC_API_KEY=sk-ant-xxxxx
ALPACA_API_KEY=xxxxx
ALPACA_SECRET_KEY=xxxxx
FRED_API_KEY=xxxxx
STRIPE_SECRET_KEY=sk_test_xxxxx
CLERK_SECRET_KEY=xxxxx
```

## Nota
Las llaves de la app son las mismas en ambas laptops; cópialas a mano desde el
`.env.dev` de tu compu principal. Lo único que cambia entre máquinas es
`DB_HOST` (y el `DB_PASS` admin si pusiste otro en la Nitro).
