import hashlib, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image, ImageOps
from flask import request
from .extensions import db
from .models import Submission

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

def ensure_dirs(app):
    base = Path(app.config["DATA_DIR"])
    for x in ("filters", "uploads", "rendered"):
        (base/x).mkdir(parents=True, exist_ok=True)

def client_ip_hash(secret):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    return hashlib.sha256(f"{secret}:{ip}".encode()).hexdigest()

def validate_and_normalize(src_path, dst_path):
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max(im.size) > 5000:
            im.thumbnail((5000,5000), Image.Resampling.LANCZOS)
        im.save(dst_path, "JPEG", quality=94, optimize=True)

def cleanup_expired(app):
    days = app.config.get("RETENTION_DAYS", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = Submission.query.filter(Submission.created_at < cutoff, Submission.deleted_at.is_(None)).limit(250).all()
    base = Path(app.config["DATA_DIR"])
    changed=False
    for s in rows:
        for folder, name in (("uploads", s.original_file), ("rendered", s.rendered_file)):
            if name:
                p=base/folder/name
                try: p.unlink(missing_ok=True)
                except Exception: pass
        s.deleted_at=datetime.now(timezone.utc); changed=True
    if changed: db.session.commit()
