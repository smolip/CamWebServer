from flask import Blueprint, jsonify, current_app
from .db import get_db
from . import camera

events_bp = Blueprint('events', __name__)


@events_bp.route('/motion', methods=['POST'])
def motion():
    """Webhook od ESP32 — detekce pohybu. Bez autentizace, omezeno na LAN v nginx."""
    camera.start_stream(current_app.config['ESP32_IP'], current_app.config['MEDIAMTX_HOST'], delay=7)
    db = get_db()
    cur = db.execute("INSERT INTO events (source) VALUES ('pir')")
    db.commit()
    camera.current_event_id = cur.lastrowid
    return jsonify({'ok': True})


@events_bp.route('/idle', methods=['POST'])
def idle():
    """Webhook od ESP32 — klid, ESP32 jde do deep sleep."""
    camera.stop_stream(force=False)
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
