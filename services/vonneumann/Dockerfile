FROM python:3.12.14-slim-bookworm@sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a
ENV PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 VN_SERVICE_MODE=closed
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip --isolated install --require-hashes --only-binary=:all: -r requirements.txt
COPY vonneumann ./vonneumann
COPY tools/native_tls_preflight.py ./tools/native_tls_preflight.py
COPY tools/native_session_canary.py ./tools/native_session_canary.py
COPY start-worker.sh ./start-worker.sh
RUN chmod 0555 start-worker.sh && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin dashboard
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/start-worker.sh"]
