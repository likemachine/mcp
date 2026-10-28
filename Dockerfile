FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-docker.txt /app/requirements-docker.txt
COPY wheelhouse/ /wheelhouse/

RUN python -m pip install \
    --no-cache-dir \
    --no-index \
    --find-links=/wheelhouse \
    -r /app/requirements-docker.txt \
    && rm -rf /wheelhouse

COPY server.py db.py schema_tools.py sql_validator.py query_tools.py /app/
COPY check_mcp.py check_schema.py check_describe.py check_stats.py check_query.py check_explain.py check_runtime.py /app/
COPY check_security.py check_query_mcp.py /app/
COPY tests/ /app/tests/

CMD ["python", "server.py"]
