# The MirrorGuard API server and command line tool.
FROM python:3.12-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 1000 mirrorguard
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
USER mirrorguard
WORKDIR /home/mirrorguard
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["mirrorguard", "serve", "--host", "0.0.0.0", "--port", "8000"]
