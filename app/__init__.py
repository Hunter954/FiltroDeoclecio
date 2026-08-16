import os, shutil
from pathlib import Path
from flask import Flask
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash
from .extensions import db, login_manager
from .models import AdminUser, Filter
from .routes import public_bp, admin_bp
from .utils import ensure_dirs, cleanup_expired

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    db_url = os.getenv("DATABASE_URL", "sqlite:////tmp/deoclecio.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-change-me"),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024,
        DATA_DIR=os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")),
        RETENTION_DAYS=int(os.getenv("RETENTION_DAYS", "30")),
        SITE_NAME=os.getenv("SITE_NAME", "Deoclécio Duarte 44222"),
    )
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin.login"
    csrf.init_app(app)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    with app.app_context():
        ensure_dirs(app)
        db.create_all()
        _bootstrap(app)
        cleanup_expired(app)
    return app


def _bootstrap(app):
    email = os.getenv("ADMIN_EMAIL", "admin@campanha.com.br").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "admin44222")
    if not AdminUser.query.filter_by(email=email).first():
        db.session.add(AdminUser(name="Administrador", email=email, password_hash=generate_password_hash(password)))
        db.session.commit()

    if Filter.query.count() == 0:
        root = Path(__file__).resolve().parent.parent
        seed = root / "seed_assets"
        target = Path(app.config["DATA_DIR"]) / "filters"
        target.mkdir(parents=True, exist_ok=True)
        overlay = target / "moldura-deoclecio.png"
        example = target / "exemplo-deoclecio.png"
        if (seed / "moldura-deoclecio.png").exists(): shutil.copy2(seed / "moldura-deoclecio.png", overlay)
        if (seed / "exemplo-deoclecio.png").exists(): shutil.copy2(seed / "exemplo-deoclecio.png", example)
        f = Filter(
            name="Deoclécio Duarte 44222",
            slug="deoclecio-44222",
            headline="O Paraná de gente que trabalha",
            subheadline="Mostre seu apoio nas redes sociais com uma foto de perfil personalizada.",
            overlay_file=overlay.name,
            example_file=example.name,
            is_active=True,
            is_featured=True,
            primary_color="#0758E8",
            accent_color="#FFC629",
        )
        db.session.add(f); db.session.commit()
