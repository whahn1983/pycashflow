# syntax=docker/dockerfile:1

FROM python:3.11-alpine

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

# Give execution rights on the cron script
RUN chmod 0644 getemail.sh

#Run Cron
ADD crontab.txt /crontab.txt
ADD getemail.sh /getemail.sh
COPY entry.sh /entry.sh
RUN chmod +x /getemail.sh /entry.sh
RUN /usr/bin/crontab /crontab.txt

ENV PYTHONPATH=/app

EXPOSE 5000

CMD ["/entry.sh"]
