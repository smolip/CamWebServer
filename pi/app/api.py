import glob
import os
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required
from .db import get_db
from . import camera

api_bp = Blueprint('api', __name__)


@api_bp.route('/stream/start', methods=['POST'])
@login_required
def stream_start():
    started = camera.start_stream(current_app.config['ESP32_IP'])
    if started:
        db = get_db()
        cur = db.execute("INSERT INTO events (source) VALUES ('manual')")
        db.commit()
        camera.current_event_id = cur.lastrowid
    return jsonify({'ok': True, 'started': started})


@api_bp.route('/stream/stop', methods=['POST'])
@login_required
def stream_stop():
    camera.stop_stream()
    event_id = camera.current_event_id
    if event_id:
        db = get_db()
        db.execute("""
            UPDATE events
            SET ended_at   = strftime('%Y-%m-%dT%H:%M:%S','now'),
                duration_s = CAST((julianday('now') - julianday(triggered_at)) * 86400 AS INTEGER)
            WHERE id = ?
        """, (event_id,))
        db.commit()
        camera.current_event_id = None
    return jsonify({'ok': True})


@api_bp.route('/stream/status')
@login_required
def stream_status():
    return jsonify(camera.get_status())


@api_bp.route('/recordings')
@login_required
def recordings():
    recs_dir = current_app.config['RECS_DIR']
    files = sorted(
        glob.glob(os.path.join(recs_dir, '**', '*.mp4'), recursive=True),
        reverse=True,
    )
    return jsonify([os.path.relpath(f, recs_dir) for f in files])


@api_bp.route('/events')
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
    items = [dict(r) for r in rows[:per_page]]
    return jsonify({'events': items, 'page': page, 'has_next': has_next})
