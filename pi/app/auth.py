from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, UserMixin
from werkzeug.security import check_password_hash
from . import login_manager

auth_bp = Blueprint('auth', __name__)


class StaticUser(UserMixin):
    id = 'admin'


@login_manager.user_loader
def load_user(user_id):
    if user_id == 'admin':
        return StaticUser()
    return None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        admin_hash = current_app.config.get('ADMIN_HASH', '')
        if (username == current_app.config.get('ADMIN_USER', 'admin')
                and admin_hash
                and check_password_hash(admin_hash, password)):
            login_user(StaticUser(), remember=True)
            return redirect(request.args.get('next') or url_for('views.index'))
        flash('Nesprávné přihlašovací údaje.', 'error')
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
