FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY src /app/src
RUN python -m pip install .

RUN useradd --create-home --uid 10001 rakuxq
USER rakuxq

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "rakuxq_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
