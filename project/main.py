from flask import Flask
from flask_login import login_required, current_user
from flask import Blueprint, render_template
from .models import Schedule

main = Blueprint('main', __name__)

@main.route('/')
@login_required
def index():
    return render_template('index.html')

@main.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@main.route('/schedule')
@login_required
def schedule():
    schedule = Schedule.query
    return render_template('bootstrap_table.html', title='Bootstrap Table',
                           schedule=schedule)

# if __name__ == "__main__":
#    app.run(host="127.0.0.1", port=8080, debug=True)

