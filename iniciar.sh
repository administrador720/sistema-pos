#!/usr/bin/env bash
# Inicia el POS en modo desarrollo (crea el entorno de Python la primera vez).
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Preparando el entorno la primera vez..."
  python3 -m venv .venv && .venv/bin/pip install -q -r backend/requirements.txt || exit 1
fi
exec .venv/bin/python launcher.py "$@"
