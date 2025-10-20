# syntax=docker/dockerfile:1

FROM python:3.14.0-alpine

ARG DOCKER_TAG
ENV APP_VERSION=$DOCKER_TAG

WORKDIR /app

COPY requirements.txt requirements.txt
# RUN pip3 install -r requirements.txt
# install everything except greenlet (ignore failure)
RUN pip install --no-cache-dir -r requirements.txt || true

COPY . .

#Run Cron
ADD crontab.txt /crontab.txt
COPY entry.sh /entry.sh
RUN chmod +x /entry.sh
RUN /usr/bin/crontab /crontab.txt

RUN apk --no-cache add curl

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/app/data/db.sqlite

HEALTHCHECK CMD curl --fail http://localhost:5000

EXPOSE 5000

CMD ["/entry.sh"]
