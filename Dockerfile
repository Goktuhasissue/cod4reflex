FROM python:3.11-slim

RUN apt-get update && apt-get install -y wget tar && \
    wget -qO- https://github.com/ekzhang/bore/releases/download/v0.5.2/bore-v0.5.2-x86_64-unknown-linux-musl.tar.gz | tar xz -C /usr/local/bin && \
    apt-get clean

WORKDIR /app
COPY server.py .
EXPOSE 8000
CMD ["python", "-u", "server.py"]
