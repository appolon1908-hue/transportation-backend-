FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system freight && adduser --system --ingroup freight freight

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

USER freight
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
