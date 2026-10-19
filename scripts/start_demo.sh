#!/usr/bin/env bash
# ==============================================================================
# SightLine AI - Unified Demo Startup Script
# Starts the verified FastAPI backend serving both API routes and built frontend
# ==============================================================================

set -e

PORT=${PORT:-8000}
HOST=${HOST:-"127.0.0.1"}
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "======================================================================"
echo "          SightLine AI - Local Review Demo Startup"
echo "======================================================================"
echo "Project Root: ${REPO_ROOT}"
echo "Target Host : http://${HOST}:${PORT}"
echo ""

# 1. Verify Model Checksum Integrity
MODEL_FILE="${REPO_ROOT}/backend/models/best.pt"
EXPECTED_SHA="0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8"

if [ ! -f "${MODEL_FILE}" ]; then
    echo "[-] ERROR: Model weights file not found at ${MODEL_FILE}"
    echo "    Please see docs/SETUP.md for private model provisioning instructions."
    exit 1
fi

echo "[1/5] Verifying neural model integrity..."
ACTUAL_SHA=$(shasum -a 256 "${MODEL_FILE}" | awk '{print $1}')
if [ "${ACTUAL_SHA}" != "${EXPECTED_SHA}" ]; then
    echo "[-] ERROR: Model SHA-256 mismatch!"
    echo "    Expected: ${EXPECTED_SHA}"
    echo "    Observed: ${ACTUAL_SHA}"
    exit 1
fi
echo "      ✓ Checksum verified: ${ACTUAL_SHA:0:16}..."

# 2. Check Python Virtual Environment
VENV_PYTHON="${REPO_ROOT}/qa/.venv/bin/python"
if [ ! -f "${VENV_PYTHON}" ]; then
    PYTHON_BIN=${PYTHON_BIN:-python3.12}
    if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
        echo "[-] Python 3.12 is required. Install it or set PYTHON_BIN to its executable."
        exit 1
    fi
    "${PYTHON_BIN}" -m venv "${REPO_ROOT}/qa/.venv"
fi
"${VENV_PYTHON}" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Use a Python 3.12 virtual environment"'
"${VENV_PYTHON}" -m pip install -r "${REPO_ROOT}/backend/requirements.txt"
echo "[2/5] Python environment verified."

# 3. Build the current frontend so repairs are visible after every restart.
echo "[3/5] Building current frontend production bundle..."
cd "${REPO_ROOT}"
npm run build

# 4. Prepare Storage Directories
mkdir -p "${REPO_ROOT}/backend/storage/media/videos"
mkdir -p "${REPO_ROOT}/backend/storage/media/keyframes"
mkdir -p "${REPO_ROOT}/backend/storage/media/temp"
echo "[4/5] Storage directories ready."

# 5. Launch FastAPI Application
echo "[5/5] Launching SightLine AI Unified Production Server on port ${PORT}..."
echo "      Serving API routes at /api/v1 and Production UI at /"
echo ""
echo "----------------------------------------------------------------------"
echo "  Live Demo URL: http://${HOST}:${PORT}"
echo "  API Docs     : http://${HOST}:${PORT}/docs"
echo "  Account      : Your unique username"
echo "  Security PIN : Choose your own in Security contacts & location"
echo "----------------------------------------------------------------------"
echo "Press Ctrl+C to stop the server."
echo ""

cd "${REPO_ROOT}/backend"
exec "${VENV_PYTHON}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}"
