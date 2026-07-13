"""
Feed de noticias IMPERSONAL (M-Noticias).

Mismo modelo que /signals: el feed es idéntico para todos los tenants. Hechos
públicos de terceros (Benzinga vía Alpaca), cacheados en una tabla COMPARTIDA
(noticias_cache). NUNCA mira la cartera del usuario.

⚠️ Client-safe: este paquete NO importa el auto-trader (engine/internal/workers).
Solo usa config, borsenhirn.db, circuit_breaker y (lazy) el SDK de Alpaca.
"""
