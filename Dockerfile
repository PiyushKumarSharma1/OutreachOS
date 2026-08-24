FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ./ && pip install --no-cache-dir fastapi uvicorn

EXPOSE 8000
CMD ["python", "-m", "outreachos.api"]
