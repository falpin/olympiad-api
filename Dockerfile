FROM python:3.9-slim

ARG SERVICE_NAME
ARG CONTAINER_PORT
ARG MAIN_DOMAIN

# Преобразуем ARG в ENV для runtime
ENV SERVICE_NAME=$SERVICE_NAME \
    CONTAINER_PORT=$CONTAINER_PORT \
    MAIN_DOMAIN=$MAIN_DOMAIN

WORKDIR /var/www/${SERVICE_NAME}${MAIN_DOMAIN}

VOLUME /var/www/${SERVICE_NAME}{MAIN_DOMAIN}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN find . -type d -name "__pycache__" -exec rm -rf {} + && \
    find . -type f -name "*.py[co]" -delete

CMD ["gunicorn", "--config", "gunicorn.conf.py", "api:app"]