FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG INSTALL_DEV=false

RUN addgroup --system servicepilot \
    && adduser --system --ingroup servicepilot --home /home/servicepilot servicepilot

COPY pyproject.toml README.md ./
COPY app ./app
COPY conversation ./conversation
COPY data ./data
RUN python -m pip install --upgrade pip \
    && if [ "$INSTALL_DEV" = "true" ]; then python -m pip install '.[test]'; else python -m pip install .; fi

USER servicepilot

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --host ${SERVICEPILOT_HOST:-0.0.0.0} --port ${PORT:-${SERVICEPILOT_PORT:-8000}}"]
