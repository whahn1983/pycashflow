![logo](./app/static/apple-touch-icon.png)
# pycashflow
[![Build Status](https://scrutinizer-ci.com/g/whahn1983/pycashflow/badges/build.png?b=master)](https://scrutinizer-ci.com/g/whahn1983/pycashflow/build-status/master)
![Docker Pulls](https://img.shields.io/docker/pulls/whahn1983/pycashflow)
![GitHub License](https://img.shields.io/github/license/whahn1983/pycashflow)

Python Flask application for future cash flow calculation and management.

* Ability to set schedule of recurring expenses and income
* Ability to manually set updated balance for the day
* List upcoming transactions (expenses/incomes) for next 60 days
* Hold transactions that have not yet posted on schedule
* Skip a future transaction from the transactions table
* Plot future cash flow out to up to 1 year
* Enable reading emails via IMAP to search for balance alerts from bank to automatically update balance
* User management with guest user access to view cash flow plot only
* Import/Export CSV of the schedule table
* Passkey Support through Corbado


<img width="912" height="880" alt="image" src="https://github.com/user-attachments/assets/72acb38c-1e60-474e-8d86-b25854d83e59" />


<br />

For Docker Support:

https://hub.docker.com/r/whahn1983/pycashflow
```
docker pull whahn1983/pycashflow:latest
```
```
docker run -d -p 127.0.0.1:5000:5000 -v /mnt/data:/app/app/data --restart always --pull always --name pycashflow whahn1983/pycashflow:latest
```

<br />

For proper date management for the calculations, consider mounting the correct local time with 
```
-v /etc/localtime:/etc/localtime:ro
```
<br />

Also consider mounting the Flask Migrate folder to save your database migration files with 

```
-v /mnt/migrations:/app/migrations
```
<br />

For Passkey support, ensure a .env file with your Corbado API key and Project ID is mounted 

```
-v /mnt/.env:/app/app/.env
```

<br />

<br />

For manual Installation:

To install, clone the git repo onto your server.  Leverage a WSGI server, like waitress or gunicorn, to run the flask application.  Optionally leverage a reverse proxy with Apache or Nginx to the WSGI server.  To support automatic database migrations, run flask-migrate commands to generate an initial version configuration.  For the automatic balance updates with email, set up cron to execute getemail.py on a regular schedule.  Ensure your email account is properly configured under Profile in the flask application.

To update, pull the latest version from git.  If database changes were necessary, leverage flask-migrate commands to migrate and update your database.  Restart the service.

<br />

<br />

Built with:

[<img src="https://resources.jetbrains.com/storage/products/company/brand/logos/PyCharm.png" alt="PyCharm logo." width="300" media="(prefers-color-scheme: light)">](https://jb.gg/OpenSourceSupport)
