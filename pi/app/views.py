from flask import Blueprint, render_template, request
from flask_login import login_required
from .db import get_db

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
@login_required
def index():
    return render_template('index.html')


@views_bp.route('/events')
@login_required
def events():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 20
    offset = (page - 1) * per_page
    db = get_db()
    rows = db.execute(
        "SELECT * FROM events ORDER BY triggered_at DESC LIMIT ? OFFSET ?",
        (per_page + 1, offset),
    ).fetchall()
    has_next = len(rows) > per_page
    items = rows[:per_page]
    return render_template('events.html', events=items, page=page, has_next=has_next)


@views_bp.route('/recordings')
@login_required
def recordings_page():
    return render_template('recordings.html')
