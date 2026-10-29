#!/usr/bin/env bash
# lm-fingerprint 引导脚本：首次运行自动创建 venv 并安装 lmfpd，之后直接复用。
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$SKILL_DIR/.venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "[lm-fingerprint] 初始化运行环境（一次性，约 30-60 秒）..." >&2
  python3 -m venv "$VENV" || { echo "错误: 无法创建 venv，请确认已安装 python3" >&2; exit 2; }
  "$VENV/bin/pip" install -q --disable-pip-version-check --upgrade pip || true
fi

if ! "$PY" -c "import lmfpd" 2>/dev/null; then
  echo "[lm-fingerprint] 安装 lmfpd SDK..." >&2
  "$VENV/bin/pip" install -q --disable-pip-version-check lmfpd || {
    echo "错误: 安装 lmfpd 失败（网络问题？）。可手动运行: $VENV/bin/pip install lmfpd" >&2
    exit 2
  }
fi

exec "$PY" "$SKILL_DIR/scripts/lmfpd_tool.py" "$@"
