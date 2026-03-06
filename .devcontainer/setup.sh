#!/bin/bash
set -e
echo "🚀 Nexus Core: Restaurando entorno..."

# Instalar dependencias Python
pip install supabase requests websocket-client huggingface_hub watchdog gradio 2>/dev/null

# Instalar dependencias Node
npm install -g pm2 2>/dev/null

# Restaurar datos de HuggingFace si hay token
if [ -f ".env" ]; then
    source .env
fi

if [ -n "$HF_TOKEN" ]; then
    echo "📦 Descargando knowledge base de HuggingFace..."
    huggingface-cli download israel-nexus/knowledge-base --local-dir ./knowledge --token "$HF_TOKEN" 2>/dev/null || echo "Dataset no encontrado aún"
fi

if [ -n "$SUPABASE_URL" ]; then
    echo "🧠 Verificando conexión Supabase..."
    python3 scripts/auto_restore.py 2>/dev/null || echo "Restore pendiente"
fi

echo "✅ Nexus Core listo."
