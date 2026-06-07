"""
dashboard_m5_patch.py
Parche para agregar el panel de M5 al dashboard existente.
Corre esto UNA vez: python dashboard_m5_patch.py
Modifica dashboard.py en tu carpeta actual.
"""
import re, os, sys

PATCH_MARKER = "# ── Footer ──"

M5_SECTION = '''
# ── M5: AI Assistant panel ───────────────────────────────────────────────────
st.markdown('<div class="section-title">AI Assistant · Hirn</div>', unsafe_allow_html=True)

col_chat, col_commands = st.columns([3, 1])

with col_chat:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Mostrar historial
    for msg in st.session_state.chat_history[-6:]:
        role_color = "#3dd68c" if msg["role"] == "assistant" else "#5b9bd5"
        role_label = "Hirn" if msg["role"] == "assistant" else "Tú"
        st.markdown(f"""
        <div style="background:#0f1628; border:1px solid #1e2d4a; border-radius:8px;
                    padding:12px 16px; margin-bottom:8px;
                    font-family:'IBM Plex Mono',monospace; font-size:12px;">
            <span style="color:{role_color}; font-weight:600; font-size:11px;
                         text-transform:uppercase; letter-spacing:0.08em;">{role_label}</span>
            <div style="color:#c8d6e8; margin-top:6px; line-height:1.6; white-space:pre-wrap;">{msg["content"]}</div>
        </div>
        """, unsafe_allow_html=True)

    # Input
    user_msg = st.text_input(
        "Pregúntale a Hirn...",
        key="hirn_input",
        placeholder="ej: ¿Cómo va el portafolio hoy? | /analisis | /mejoras | /idea comprar OXY"
    )

    col_send, col_clear = st.columns([1, 1])
    with col_send:
        if st.button("Enviar →", key="hirn_send"):
            if user_msg.strip():
                with st.spinner("Hirn pensando..."):
                    try:
                        import subprocess, json as _json
                        result = subprocess.run(
                            ["python", "m5_assistant.py", "--once", user_msg],
                            capture_output=True, text=True, timeout=60,
                            cwd=os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else "."
                        )
                        reply = result.stdout.strip() or result.stderr.strip() or "Sin respuesta."
                    except Exception as e:
                        reply = f"Error conectando con el asistente: {e}"

                st.session_state.chat_history.append({"role": "user", "content": user_msg})
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
                st.rerun()

    with col_clear:
        if st.button("Limpiar chat", key="hirn_clear"):
            st.session_state.chat_history = []
            st.rerun()

with col_commands:
    st.markdown("""
    <div style="background:#0f1628; border:1px solid #1e2d4a; border-radius:10px;
                padding:16px; font-family:'IBM Plex Mono',monospace;">
        <div style="font-size:11px; color:#4a6fa5; text-transform:uppercase;
                    letter-spacing:0.1em; margin-bottom:12px;">Comandos rápidos</div>
    </div>
    """, unsafe_allow_html=True)

    quick_commands = [
        ("📊 Análisis",    "/analisis"),
        ("💡 Mejoras",     "/mejoras"),
        ("📈 Win rate",    "¿Cuál es mi win rate histórico y cómo mejorarlo?"),
        ("🐋 Whales",      "¿Qué oportunidades de whale copy son más relevantes ahora?"),
        ("⚠️ Alertas",     "¿Hay algo en el portafolio que debería atender urgentemente?"),
        ("🎯 Estrategia",  "¿Qué estrategia recomiendas para el régimen actual?"),
    ]

    for label, cmd in quick_commands:
        if st.button(label, key=f"quick_{label}"):
            with st.spinner("Hirn pensando..."):
                try:
                    import subprocess
                    result = subprocess.run(
                        ["python", "m5_assistant.py", "--once", cmd],
                        capture_output=True, text=True, timeout=60,
                        cwd=os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else "."
                    )
                    reply = result.stdout.strip() or result.stderr.strip() or "Sin respuesta."
                except Exception as e:
                    reply = f"Error: {e}"

            st.session_state.chat_history.append({"role": "user", "content": cmd})
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()

'''

def apply_patch(dashboard_path: str):
    if not os.path.exists(dashboard_path):
        print(f"❌ No encontré {dashboard_path}")
        print("   Asegúrate de correr este script desde la carpeta proyecto_trading/")
        return False

    with open(dashboard_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "AI Assistant · Hirn" in content:
        print("ℹ️  El parche ya fue aplicado anteriormente.")
        return True

    if PATCH_MARKER not in content:
        print(f"❌ No encontré el marcador '{PATCH_MARKER}' en dashboard.py")
        print("   El dashboard podría tener una versión diferente.")
        return False

    # Insertar la sección M5 antes del footer
    new_content = content.replace(PATCH_MARKER, M5_SECTION + PATCH_MARKER)

    # Backup
    backup_path = dashboard_path + ".backup"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Backup guardado en {backup_path}")

    with open(dashboard_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print("✅ Parche M5 aplicado exitosamente a dashboard.py")
    print("   Recarga el dashboard en tu navegador para ver el panel de Hirn.")
    return True


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    dashboard_path = os.path.join(base, "dashboard.py")
    apply_patch(dashboard_path)