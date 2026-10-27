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

COPY server.py check_mcp.py /app/

CMD ["python", "server.py"]
