FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress fonts-wqy-zenhei libseccomp2 && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home converter
COPY server.py /app/server.py
ARG APP_BUILD_VERSION=development
LABEL org.opencontainers.image.revision=$APP_BUILD_VERSION
USER 10001:10001
ENV HOME=/tmp
EXPOSE 8090
CMD ["python", "/app/server.py"]
