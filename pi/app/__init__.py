import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager

login_manager = LoginManager()


def create_app():
    base_dir = os.path.dirname(os.path.dirname(__file__))  # pi/

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
    )

    app.config.update(
        SECRET_KEY=os.environ.get('CAM_SECRET_KEY', 'dev-secret-change-me'),
        DATABASE=os.environ.get('DATABASE', os.path.join(base_dir, 'cam.db')),
        RECS_DIR=os.environ.get('RECS_DIR', '/home/pi/recordings'),
        ESP32_IP=os.environ.get('ESP32_IP', '192.168.1.50'),
        MEDIAMTX_HOST=os.environ.get('MEDIAMTX_HOST', 'localhost'),
        ADMIN_USER=os.environ.get('CAM_USER', 'admin'),
        ADMIN_HASH=os.environ.get('CAM_HASH', ''),
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=30 * 24 * 3600,
    )

    config_file = os.path.join(base_dir, 'config.py')
    if os.path.exists(config_file):
        app.config.from_pyfile(config_file)

    # Správné IP adresy přes VPS → WireGuard → RPi proxy řetěz
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    from .db import init_app as db_init_app
    db_init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Přihlaste se pro přístup.'
    login_manager.login_message_category = 'info'

    from .auth import auth_bp
    from .views import views_bp
    from .api import api_bp
    from .events import events_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(events_bp)

    return app
