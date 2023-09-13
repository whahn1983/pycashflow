#!/bin/sh

# start cron
/usr/sbin/crond -f -l 8 && /usr/local/bin/flask --app app db migrate && /usr/local/bin/waitress-serve --listen=127.0.0.1:5000 --call app:create_app & disown

#flask migrate


#run waitress

