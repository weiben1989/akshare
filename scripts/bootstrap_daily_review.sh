#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DATE_ARG="${DATE:-}"
EXPORT_DIR="${EXPORT_DIR:-out}"
CONFIG_PATH="${CONFIG:-}"

log() {
  printf '[daily-review] %s\n' "$*"
}

if [ ! -d "${ROOT_DIR}/${VENV_DIR}" ]; then
  log "creating virtual environment at ${ROOT_DIR}/${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${ROOT_DIR}/${VENV_DIR}"
fi

if [ -f "${ROOT_DIR}/${VENV_DIR}/bin/activate" ]; then
  # shellcheck disable=SC1090
  source "${ROOT_DIR}/${VENV_DIR}/bin/activate"
elif [ -f "${ROOT_DIR}/${VENV_DIR}/Scripts/activate" ]; then
  # shellcheck disable=SC1090
  source "${ROOT_DIR}/${VENV_DIR}/Scripts/activate"
else
  echo "无法找到虚拟环境激活脚本：${ROOT_DIR}/${VENV_DIR}" >&2
  exit 1
fi

if [ "${SKIP_INSTALL:-0}" = "0" ]; then
  log "installing project dependencies"
  python -m pip install --upgrade pip
  python -m pip install -e "${ROOT_DIR}"
fi

ARGS=()
if [ -n "${DATE_ARG}" ]; then
  ARGS+=(--date "${DATE_ARG}")
fi
if [ -n "${CONFIG_PATH}" ]; then
  ARGS+=(--config "${CONFIG_PATH}")
fi
if [ "${ENABLE_DEEPSEEK:-0}" = "1" ]; then
  ARGS+=(--enable-deepseek)
fi
if [ "${DISABLE_DEEPSEEK:-0}" = "1" ]; then
  ARGS+=(--disable-deepseek)
fi
ARGS+=(--export "${EXPORT_DIR}")

log "running daily review pipeline"
log "python ${ROOT_DIR}/run_daily.py ${ARGS[*]}"
python "${ROOT_DIR}/run_daily.py" "${ARGS[@]}"
