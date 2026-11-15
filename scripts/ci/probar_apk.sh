#!/usr/bin/env bash
# Se ejecuta DENTRO del emulador de Android (ver .github/workflows/release.yml): instala el APK de depuración, levanta
# el servidor del computador con datos de demostración y recorre la app con scripts/ci/probar_apk.py.
set -euo pipefail
APK="$1"
export POS_DATA_DIR="$RUNNER_TEMP/pos-datos-apk" POS_SIN_JOBS=1 POS_PUERTO_MOVIL=8766 POS_HOST_MOVIL=0.0.0.0 POS_DIRECCIONES_MOVIL=10.0.2.2
rm -rf "$POS_DATA_DIR"
(cd backend && python -m app.seed_demo --dias 3 --ventas-dia 10 --forzar >/dev/null)
(cd backend && nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --log-level warning > "$RUNNER_TEMP/servidor-apk.log" 2>&1 &)
for i in $(seq 1 40); do curl -sf http://127.0.0.1:8765/api/salud >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8765/api/salud
adb install -r "$APK"
EAN=$(cd backend && python -c "from app.seed_demo import ean13; print(ean13(1))")
python scripts/ci/probar_apk.py --admin http://127.0.0.1:8765 --usuario admin --clave demo1234 --producto "$EAN" --nombre "Leche"
