#!/usr/bin/env bash
# Inicia el POS en Linux o macOS (crea el entorno de Python la primera vez).
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Preparando el programa por primera vez..."
  python3 -m venv .venv && .venv/bin/pip install -q -r backend/requirements.txt || exit 1
  for p in pywebview pyserial; do .venv/bin/pip install -q "$p" 2>/dev/null || echo "Aviso: no se pudo instalar $p (opcional)"; done
fi
exec .venv/bin/python launcher.py "$@"
