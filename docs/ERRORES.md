# ERRORES — bitácora
> Formato: error -> causa -> fix -> lección

### [2026-06-01] ImportError: _get_conn en main.py
- Causa: función borrada en refactor 5.4.a, seguía importada
- Fix: quitar el import
- Lección: verificar con ast.parse antes de dar por cerrado
