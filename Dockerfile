FROM node:20-alpine AS web-build
WORKDIR /build/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
COPY --from=web-build /build/web/dist ./web/dist
EXPOSE 8000
CMD ["sh", "-c", "test -f qadam/data/corpus/leadership.jsonl || python -m qadam.data.generate; test -f qadam/data/model/leadership.joblib || python -m eval.train; exec python -m uvicorn qadam.api.main:app --host 0.0.0.0 --port ${PORT}"]
