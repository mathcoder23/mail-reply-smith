FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip3 install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install

COPY src ./src

CMD ["python", "src/main.py","--config","/app/src/config/config.yaml"]