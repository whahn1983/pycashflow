from flask import Flask
from flask_login import login_required, current_user
from flask import Blueprint, render_template

main = Blueprint('main', __name__)

@main.route('/')
@login_required
def index():
    return render_template('index.html')

@main.route('/profile')
@login_required
def profile():
    return render_template('profile.html')


# if __name__ == "__main__":
#    app.run(host="127.0.0.1", port=8080, debug=True)

