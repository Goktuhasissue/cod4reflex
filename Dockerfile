FROM python:3.11-slim
WORKDIR /app
COPY server.py .
EXPOSE 3074
CMD ["python", "-u", "server.py"]
