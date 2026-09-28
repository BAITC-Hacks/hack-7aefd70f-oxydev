#!/usr/bin/env bash
# Запуск Qadam AI одной командой: ./run.sh
#
# Шаги идемпотентные: что уже сделано, повторно не делается.
#   1. зависимости Python
#   2. корпус (если его нет)
#   3. обучение и отчёт о валидации (если модели нет)
#   4. сборка фронта (если есть npm)
#   5. сервер на http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
PORT="${PORT:-8000}"
PIP_FLAGS="${PIP_FLAGS:-}"

echo "== 1/5 зависимости =="
if ! $PY -c "import fastapi, sklearn, pydantic" 2>/dev/null; then
  $PY -m pip install -q $PIP_FLAGS -r requirements.txt
fi

echo "== 2/5 корпус =="
if [ ! -f qadam/data/corpus/leadership.jsonl ]; then
  $PY -m qadam.data.generate
else
  echo "корпус на месте: qadam/data/corpus/leadership.jsonl"
fi

echo "== 3/5 обучение и валидация =="
if [ ! -f qadam/data/model/leadership.joblib ]; then
  $PY -m eval.train
else
  echo "модель на месте: qadam/data/model/leadership.joblib (переобучить: python3 -m eval.train)"
fi

echo "== 4/5 интерфейс =="
if command -v npm >/dev/null 2>&1; then
  if [ ! -d web/node_modules ]; then (cd web && npm install --silent); fi
  if [ ! -d web/dist ]; then (cd web && npm run build); fi
else
  echo "npm не найден — интерфейс пропущен, API и CLI работают"
fi

echo "== 5/5 сервер =="
echo "интерфейс и API: http://127.0.0.1:${PORT}"
exec $PY -m uvicorn qadam.api.main:app --host 127.0.0.1 --port "${PORT}"
