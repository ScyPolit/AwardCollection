FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN sed -i 's@http://deb.debian.org/debian@https://mirrors.ustc.edu.cn/debian@g' /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends libpq5 fonts-noto-cjk fonts-wqy-zenhei chromium gosu && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home award
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt constraints.txt ./
COPY .offline-wheels/ /tmp/offline-wheels/
COPY wheel-assets/ ./wheel-assets/
COPY tools/verify_wheel_cache.py ./tools/verify_wheel_cache.py
RUN if [ -f /tmp/offline-wheels/READY ]; then python tools/verify_wheel_cache.py --root /tmp/offline-wheels --manifest wheel-assets/manifest.json && pip install --no-cache-dir --no-index --find-links=/tmp/offline-wheels -r requirements.txt -c constraints.txt; else pip install --no-cache-dir --retries 8 --timeout 60 -r requirements.txt -c constraints.txt; fi && rm -rf /tmp/offline-wheels
COPY font-assets ./font-assets
COPY tools/prepare_fonts.py ./tools/prepare_fonts.py
RUN python tools/prepare_fonts.py && rm -rf /app/.tmp-font-downloads
COPY config ./config
COPY awards ./awards
COPY manage.py entrypoint.sh ./
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh
RUN mkdir -p /app/staticfiles && chown -R award:award /app/staticfiles
ARG APP_BUILD_VERSION=development
LABEL org.opencontainers.image.revision=$APP_BUILD_VERSION
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.asgi:application", "--worker-class", "uvicorn_worker.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
