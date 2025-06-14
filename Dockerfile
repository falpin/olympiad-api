FROM python:3.9-slim

ARG SERVICE_NAME
ARG CONTAINER_PORT
ARG MAIN_DOMAIN

WORKDIR /var/www/${SERVICE_NAME}{MAIN_DOMAIN}

VOLUME /var/www/${SERVICE_NAME}{MAIN_DOMAIN}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN find . -type d -name "__pycache__" -exec rm -rf {} + && \
    find . -type f -name "*.py[co]" -delete

CMD ["gunicorn", "--bind", "0.0.0.0:${CONTAINER_PORT}", "--workers", "4", "--user", "root", "api:app"]