FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    VERIGRAPH_DEMO_BUNDLE_PATH=/app/data/demo/averitec \
    VERIGRAPH_REQUIRE_PRIVATE_CATALOG=true \
    VERIGRAPH_EMBEDDING_MODEL_PATH=/models/bge-small-en-v1.5 \
    VERIGRAPH_NLI_MODEL_PATH=/models/deberta-v3-base-mnli-fever-anli \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /app

RUN groupadd --system verigraph && useradd --system --gid verigraph verigraph

COPY backend/requirements.lock /tmp/requirements.lock
# The CPU wheel first: the same pin resolved from PyPI on Linux is the CUDA
# build, which multiplies the image size for no benefit on this workload.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
 && pip install --no-cache-dir --requirement /tmp/requirements.lock

COPY backend/verigraph_backend /app/backend/verigraph_backend
COPY scripts /app/scripts
# The approved, immutable demo bundle is versioned with the repository. Large
# model weights are mounted at /models after the explicit preparation step.
COPY data/demo/averitec /app/data/demo/averitec

RUN chown -R verigraph:verigraph /app
USER verigraph

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health', timeout=3)"

CMD ["uvicorn", "verigraph_backend.api:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]

FROM runtime AS test
USER root
COPY backend/tests /app/backend/tests
RUN pip install --no-cache-dir pytest==8.3.4 pytest-asyncio==0.25.3
USER verigraph
