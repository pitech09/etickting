FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY . .
RUN pip install --no-cache-dir .
RUN python manage.py collectstatic --noinput
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
