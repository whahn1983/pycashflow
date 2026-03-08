# syntax=docker/dockerfile:1

FROM python:3.14.3-alpine

ARG DOCKER_TAG
ENV APP_VERSION=$DOCKER_TAG

WORKDIR /app

COPY requirements.txt requirements.txt
COPY constraints.txt constraints.txt
# RUN pip3 install -r requirements.txt
# install everything except greenlet
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

RUN apk --no-cache add curl su-exec

# Create a dedicated non-root runtime user and group
RUN addgroup -S appgroup && adduser -S -G appgroup appuser

COPY . .

# Set up user-specific crontab directory for busybox crond (via -c flag)
RUN mkdir -p /app/crontabs && \
    cp crontab.txt /app/crontabs/appuser && \
    chmod 600 /app/crontabs/appuser

COPY entry.sh /entry.sh
RUN chmod +x /entry.sh

# Create SQLite data directory and log file, then hand ownership to appuser
RUN mkdir -p /app/app/data && \
    touch /var/log/getemail.log && \
    chown -R appuser:appgroup /app /entry.sh /var/log/getemail.log

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/app/data/db.sqlite

HEALTHCHECK CMD curl --fail http://localhost:5000

EXPOSE 5000

CMD ["/entry.sh"]
