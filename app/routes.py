import base64, io, os, re, secrets, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from sqlalchemy import func
from .extensions import db
from .models import AdminUser, Event, Filter, Submission
from .utils import client_ip_hash, validate_and_normalize, cleanup_expired

public_bp = Blueprint("public", __name__)
admin_bp = Blueprint("admin", __name__)


def log_event(event_type, filter_id=None, submission_id=None):
    db.session.add(Event(event_type=event_type, filter_id=filter_id, submission_id=submission_id,
                         ip_hash=client_ip_hash(current_app.config["SECRET_KEY"])))
    db.session.commit()

@public_bp.get("/")
def index():
    f = Filter.query.filter_by(is_active=True, is_featured=True).first() or Filter.query.filter_by(is_active=True).first()
    filters = Filter.query.filter_by(is_active=True).order_by(Filter.created_at.desc()).all()
    if f: log_event("page_view", f.id)
    return render_template("index.html", featured=f, filters=filters)

@public_bp.get("/f/<slug>")
def filter_page(slug):
    f = Filter.query.filter_by(slug=slug, is_active=True).first_or_404()
    log_event("page_view", f.id)
    return render_template("filter.html", featured=f, filters=[f])

@public_bp.get("/filter-asset/<int:filter_id>/<kind>")
def filter_asset(filter_id, kind):
    f = db.session.get(Filter, filter_id) or abort(404)
    name = f.overlay_file if kind == "overlay" else (f.example_file or f.overlay_file) if kind == "example" else None
    if not name: abort(404)
    p = Path(current_app.config["DATA_DIR"]) / "filters" / name
    if not p.exists(): abort(404)
    return send_file(p, max_age=3600)

@public_bp.post("/api/events")
def api_event():
    data=request.get_json(silent=True) or {}
    typ=data.get("type")
    allowed={"editor_open","upload_click","share_click"}
    if typ not in allowed: return jsonify(ok=False), 400
    f=db.session.get(Filter, int(data.get("filter_id",0)))
    if not f: return jsonify(ok=False),404
    log_event(typ,f.id)
    return jsonify(ok=True)

@public_bp.post("/api/upload")
def api_upload():
    cleanup_expired(current_app)
    f_id=request.form.get("filter_id", type=int)
    consent=request.form.get("consent") == "true"
    f=db.session.get(Filter,f_id) if f_id else None
    if not f or not f.is_active: return jsonify(error="Filtro indisponível."),404
    if not consent: return jsonify(error="É necessário aceitar o uso temporário da foto."),400
    file=request.files.get("photo")
    if not file or not file.filename: return jsonify(error="Escolha uma foto."),400
    sid=str(uuid.uuid4()); token=secrets.token_urlsafe(32)
    base=Path(current_app.config["DATA_DIR"]); temp=base/"uploads"/f"{sid}.source"
    norm=base/"uploads"/f"{sid}.jpg"
    try:
        file.save(temp)
        if temp.stat().st_size > current_app.config["MAX_CONTENT_LENGTH"]: raise ValueError("Arquivo grande demais")
        validate_and_normalize(temp, norm)
        temp.unlink(missing_ok=True)
    except Exception:
        temp.unlink(missing_ok=True); norm.unlink(missing_ok=True)
        return jsonify(error="Não foi possível ler esta imagem. Use JPG, PNG ou WEBP."),400
    s=Submission(id=sid, filter_id=f.id, access_token=token, original_file=norm.name,
                 original_name=secure_filename(file.filename)[:255], mime_type="image/jpeg",
                 size_bytes=norm.stat().st_size, ip_hash=client_ip_hash(current_app.config["SECRET_KEY"]),
                 user_agent=(request.headers.get("User-Agent") or "")[:500])
    db.session.add(s)
    db.session.add(Event(event_type="upload",filter_id=f.id,submission_id=sid,ip_hash=s.ip_hash))
    db.session.commit()
    return jsonify(submission_id=sid, token=token,
                   photo_url=url_for("public.submission_media", submission_id=sid, token=token))

@public_bp.get("/media/<submission_id>")
def submission_media(submission_id):
    s=db.session.get(Submission,submission_id) or abort(404)
    token=request.args.get("token","")
    if not secrets.compare_digest(token,s.access_token): abort(403)
    p=Path(current_app.config["DATA_DIR"])/"uploads"/s.original_file
    if not p.exists(): abort(404)
    return send_file(p, mimetype="image/jpeg", max_age=0)

@public_bp.post("/api/complete/<submission_id>")
def api_complete(submission_id):
    s=db.session.get(Submission,submission_id) or abort(404)
    data=request.get_json(silent=True) or {}
    token=data.get("token","")
    if not secrets.compare_digest(token,s.access_token): abort(403)
    image_data=data.get("image","")
    if not image_data.startswith("data:image/png;base64,"): return jsonify(error="Imagem final inválida."),400
    try:
        raw=base64.b64decode(image_data.split(",",1)[1], validate=True)
        if len(raw) > 20*1024*1024: raise ValueError()
        im=Image.open(io.BytesIO(raw)); im.verify()
        out=Path(current_app.config["DATA_DIR"])/"rendered"/f"{s.id}.png"
        out.write_bytes(raw)
    except Exception:
        return jsonify(error="Não foi possível finalizar a imagem."),400
    s.rendered_file=out.name; s.completed_at=datetime.now(timezone.utc)
    db.session.add(Event(event_type="completed",filter_id=s.filter_id,submission_id=s.id,ip_hash=s.ip_hash))
    db.session.commit()
    return jsonify(download_url=url_for("public.download", submission_id=s.id, token=s.access_token))

@public_bp.get("/download/<submission_id>")
def download(submission_id):
    s=db.session.get(Submission,submission_id) or abort(404)
    token=request.args.get("token","")
    if not secrets.compare_digest(token,s.access_token): abort(403)
    if not s.rendered_file: abort(404)
    p=Path(current_app.config["DATA_DIR"])/"rendered"/s.rendered_file
    if not p.exists(): abort(404)
    s.downloaded_at=datetime.now(timezone.utc)
    db.session.add(Event(event_type="download",filter_id=s.filter_id,submission_id=s.id,ip_hash=s.ip_hash)); db.session.commit()
    return send_file(p, mimetype="image/png", as_attachment=True, download_name=f"moldura-{s.filter.slug}.png")

@public_bp.get("/health")
def health(): return jsonify(status="ok")

# -------- Admin --------
@admin_bp.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("admin.dashboard"))
    if request.method=="POST":
        email=(request.form.get("email") or "").strip().lower(); password=request.form.get("password") or ""
        u=AdminUser.query.filter_by(email=email).first()
        if u and check_password_hash(u.password_hash,password):
            login_user(u, remember=True); u.last_login_at=datetime.now(timezone.utc); db.session.commit()
            return redirect(url_for("admin.dashboard"))
        flash("E-mail ou senha inválidos.","danger")
    return render_template("admin/login.html")

@admin_bp.post("/logout")
@login_required
def logout(): logout_user(); return redirect(url_for("admin.login"))

@admin_bp.get("")
@login_required
def dashboard():
    since=datetime.now(timezone.utc)-timedelta(days=30)
    events=Event.query.filter(Event.created_at>=since).all()
    counts={x:sum(1 for e in events if e.event_type==x) for x in ["page_view","editor_open","upload","completed","download"]}
    unique=len({e.ip_hash for e in events if e.ip_hash})
    conv=(counts["completed"]/counts["page_view"]*100) if counts["page_view"] else 0
    recent=Submission.query.order_by(Submission.created_at.desc()).limit(8).all()
    filters=Filter.query.order_by(Filter.created_at.desc()).all()
    # daily chart last 14d
    days=[]
    for i in range(13,-1,-1):
        d=(datetime.now(timezone.utc)-timedelta(days=i)).date()
        days.append({"label":d.strftime("%d/%m"),"views":0,"completed":0})
    idx={x["label"]:x for x in days}
    for e in Event.query.filter(Event.created_at>=datetime.now(timezone.utc)-timedelta(days=14)).all():
        lab=e.created_at.strftime("%d/%m")
        if lab in idx and e.event_type in ("page_view","completed"):
            idx[lab]["views" if e.event_type=="page_view" else "completed"]+=1
    return render_template("admin/dashboard.html", counts=counts, unique=unique, conv=conv, recent=recent, filters=filters, chart=days)

@admin_bp.get("/submissions")
@login_required
def submissions():
    page=request.args.get("page",1,type=int); filter_id=request.args.get("filter_id",type=int)
    q=Submission.query.order_by(Submission.created_at.desc())
    if filter_id: q=q.filter_by(filter_id=filter_id)
    pagination=q.paginate(page=page,per_page=24,error_out=False)
    return render_template("admin/submissions.html",pagination=pagination,filters=Filter.query.all(),selected=filter_id)

@admin_bp.get("/submission/<submission_id>/<kind>")
@login_required
def admin_media(submission_id,kind):
    s=db.session.get(Submission,submission_id) or abort(404)
    name=s.original_file if kind=="original" else s.rendered_file if kind=="rendered" else None
    folder="uploads" if kind=="original" else "rendered"
    if not name: abort(404)
    p=Path(current_app.config["DATA_DIR"])/folder/name
    if not p.exists(): abort(404)
    return send_file(p,max_age=0)

@admin_bp.post("/submission/<submission_id>/delete")
@login_required
def delete_submission(submission_id):
    s=db.session.get(Submission,submission_id) or abort(404)
    base=Path(current_app.config["DATA_DIR"])
    for folder,name in (("uploads",s.original_file),("rendered",s.rendered_file)):
        if name: (base/folder/name).unlink(missing_ok=True)
    s.deleted_at=datetime.now(timezone.utc); db.session.commit(); flash("Fotos removidas do volume.","success")
    return redirect(request.referrer or url_for("admin.submissions"))


def slugify(text):
    text=(text or "").lower().strip(); text=re.sub(r"[^a-z0-9áàâãéêíóôõúç -]","",text)
    trans=str.maketrans("áàâãéêíóôõúç","aaaaeeiooouc"); text=text.translate(trans)
    return re.sub(r"[-\s]+","-",text).strip("-") or secrets.token_hex(4)

@admin_bp.route("/filters", methods=["GET","POST"])
@login_required
def filters():
    if request.method=="POST":
        name=(request.form.get("name") or "").strip(); overlay=request.files.get("overlay")
        if not name or not overlay: flash("Nome e PNG da moldura são obrigatórios.","danger"); return redirect(url_for("admin.filters"))
        slug=slugify(request.form.get("slug") or name)
        if Filter.query.filter_by(slug=slug).first(): slug=f"{slug}-{secrets.token_hex(2)}"
        fid=uuid.uuid4().hex[:12]; base=Path(current_app.config["DATA_DIR"])/"filters"
        op=base/f"{fid}-overlay.png"; overlay.save(op)
        try:
            im=Image.open(op)
            if im.format!="PNG" or "A" not in im.getbands(): raise ValueError()
        except Exception:
            op.unlink(missing_ok=True); flash("A moldura precisa ser um PNG válido com transparência.","danger"); return redirect(url_for("admin.filters"))
        ex=request.files.get("example"); exname=None
        if ex and ex.filename:
            exname=f"{fid}-example.png"; ex.save(base/exname)
        if request.form.get("is_featured")=="on": Filter.query.update({Filter.is_featured:False})
        f=Filter(name=name,slug=slug,headline=request.form.get("headline") or "Mostre seu apoio",
                 subheadline=request.form.get("subheadline") or "Envie sua foto, ajuste e baixe pronta.",
                 overlay_file=op.name,example_file=exname,primary_color=request.form.get("primary_color") or "#0758E8",
                 accent_color=request.form.get("accent_color") or "#FFC629",is_active=True,
                 is_featured=request.form.get("is_featured")=="on")
        db.session.add(f); db.session.commit(); flash("Novo filtro publicado.","success"); return redirect(url_for("admin.filters"))
    return render_template("admin/filters.html",filters=Filter.query.order_by(Filter.created_at.desc()).all())

@admin_bp.post("/filters/<int:filter_id>/toggle")
@login_required
def toggle_filter(filter_id):
    f=db.session.get(Filter,filter_id) or abort(404); f.is_active=not f.is_active; db.session.commit(); return redirect(url_for("admin.filters"))

@admin_bp.post("/filters/<int:filter_id>/feature")
@login_required
def feature_filter(filter_id):
    f=db.session.get(Filter,filter_id) or abort(404); Filter.query.update({Filter.is_featured:False}); f.is_featured=True; f.is_active=True; db.session.commit(); return redirect(url_for("admin.filters"))

@admin_bp.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    if request.method=="POST":
        current=current_user; current.name=(request.form.get("name") or current.name).strip(); new_email=(request.form.get("email") or current.email).strip().lower()
        if new_email!=current.email and AdminUser.query.filter_by(email=new_email).first(): flash("Este e-mail já está em uso.","danger")
        else:
            current.email=new_email
            pw=request.form.get("password") or ""
            if pw:
                if len(pw)<10: flash("A nova senha precisa ter pelo menos 10 caracteres.","danger"); return redirect(url_for("admin.settings"))
                current.password_hash=generate_password_hash(pw)
            db.session.commit(); flash("Configurações salvas.","success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html")
