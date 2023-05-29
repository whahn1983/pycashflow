# pycashflow

Python Flask application for future cash flow calculation and management.

* Ability to set schedule of recurring expenses and income
* Ability to manually set updated balance for the day
* List upcoming transactions (expenses/incomes) for next 60 days
* Plot future cash flow out to up to 4 years
* Enable reading emails via IMAP to search for balance alerts from bank to automatically update balance

To install, clone the git repo onto your server and modify and deploy the .service file for Systemd.  Leverage a WSGI server, like waitress or gunicorn, to run the flask application.  Optionally leverage a reverse proxy with Apache or Nginx to the WSGI server.  To support automatic database migrations, run flask-migrate to generate an initial version configuration.  For the automatic balance updates with email, edit the included bash script for your configuration and set up cron to execute the .py on a regular schedule.  Ensure your email account is properly configured under Profile in the flask application.

To update, pull the latest version from git.  If database changes were necessary, leverage flask-migrate commands to migrate and update your database.  Restart the Systemd service.
