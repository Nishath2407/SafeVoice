# app.py — SafeVoice Full-Stack Application Entry Point
# Run with: python app.py

from dotenv import load_dotenv
load_dotenv()

import os, json, tempfile, secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, jsonify, redirect,
                   url_for, flash)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, SurvivorSession, ChatMessage, EscalationLog, AuditLog
from payment_models import Payment, PaymentPlan, Subscription
import emotion_model
import severity_engine


# ─────────────────────────────────────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"]                     = os.environ.get("SECRET_KEY", "safevoice-secret-2024")
app.config["SQLALCHEMY_DATABASE_URI"]        = "sqlite:///safevoice.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"]             = 32 * 1024 * 1024   # 32 MB

db.init_app(app)
app.jinja_env.filters["from_json"] = json.loads

login_manager = LoginManager(app)
login_manager.login_view             = "login"
login_manager.login_message_category = "info"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

from payments import payments_bp
app.register_blueprint(payments_bp)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for("dashboard_redirect"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def log_action(action, details=None):
    entry = AuditLog(
        actor_id   = current_user.id if current_user.is_authenticated else None,
        action     = action,
        details    = details,
        ip_address = request.remote_addr,
    )
    db.session.add(entry)
    db.session.commit()


def hash_pin(pin: str) -> str:
    import hashlib
    return hashlib.sha256(pin.strip().encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/helplines")
def helplines():
    return render_template("helplines.html")


# ─────────────────────────────────────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard_redirect"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user     = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash("Your account has been disabled. Contact admin.", "danger")
                return redirect(url_for("login"))
            if not user.is_approved:
                flash("Your account is pending admin approval.", "warning")
                return redirect(url_for("login"))
            login_user(user)
            return redirect(url_for("dashboard_redirect"))

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role     = request.form.get("role", "therapist")

        if not email or not username or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email is already registered.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username is already taken.", "danger")
            return redirect(url_for("register"))

        user = User(
            username       = username,
            email          = email,
            password_hash  = generate_password_hash(password),
            role           = role,
            full_name      = request.form.get("full_name", "").strip(),
            specialization = request.form.get("specialization", "").strip(),
            bio            = request.form.get("bio", "").strip(),
            is_approved    = (role == "emergency"),
        )
        db.session.add(user)
        db.session.commit()

        if role == "therapist":
            flash("Registration successful! Waiting for admin approval.", "success")
        else:
            flash("Account created successfully. You can now log in.", "success")

        return redirect(url_for("login"))

    return render_template("auth/register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out safely.", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard_redirect():
    routes = {
        "therapist": "therapist_dashboard",
        "admin":     "admin_dashboard",
        "emergency": "emergency_dashboard",
    }
    dest = routes.get(current_user.role)
    if not dest:
        return redirect(url_for("home"))
    return redirect(url_for(dest))


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD RESET
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user  = User.query.filter_by(email=email).first()

        # Always show the same message — never reveal whether email exists
        if user:
            token              = secrets.token_urlsafe(32)
            user.reset_token   = token
            user.reset_expires = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            reset_link = f"{request.host_url}reset-password/{token}"
            # TODO: Replace with real email sending (Flask-Mail / SendGrid)
            print(f"\n[PASSWORD RESET] Link for {email}:\n{reset_link}\n")

        flash("If that email is registered, a reset link has been sent.", "info")
        return redirect(url_for("forgot_password"))

    return render_template("auth/forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_expires or datetime.utcnow() > user.reset_expires:
        flash("This reset link is invalid or has expired. Please request a new one.", "danger")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password     = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("reset_password", token=token))

        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("reset_password", token=token))

        user.password_hash = generate_password_hash(new_password)
        user.reset_token   = None
        user.reset_expires = None
        db.session.commit()

        flash("Password reset successfully! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("auth/reset_password.html", token=token)


# ─────────────────────────────────────────────────────────────────────────────
# SURVIVOR ROUTES  (fully anonymous — no login required)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/survivor")
def survivor_home():
    return render_template("survivor/home.html")


@app.route("/survivor/analyse")
def survivor_analyse():
    return render_template("survivor/analyse.html")


@app.route("/survivor/chat/<session_uuid>")
def survivor_chat(session_uuid):
    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    if not getattr(sess, "is_paid", False):
        return redirect(f"/payment/plans/{session_uuid}")
    messages = ChatMessage.query.filter_by(
        session_id=sess.id
    ).order_by(ChatMessage.timestamp.asc()).all()
    return render_template("survivor/chat.html", session=sess, messages=messages)


@app.route("/survivor/history/<session_uuid>")
def survivor_history(session_uuid):
    sess     = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    messages = ChatMessage.query.filter_by(
        session_id=sess.id
    ).order_by(ChatMessage.timestamp.asc()).all()
    payment  = Payment.query.filter_by(
        session_uuid=session_uuid, status="paid"
    ).order_by(Payment.paid_at.desc()).first()
    return render_template("survivor/history.html",
                           session=sess, messages=messages, payment=payment)


@app.route("/survivor/emergency/<session_uuid>")
def emergency_form(session_uuid):
    """Shown after High-risk result — lets survivor add or update their safety details."""
    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    return render_template("survivor/emergency_form.html", session=sess)


# ─────────────────────────────────────────────────────────────────────────────
# SURVIVOR API — SESSION STATUS
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/session-status/<session_uuid>")
def session_status(session_uuid):
    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first()
    if not sess:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({
        "status":    sess.status,
        "risk_level": sess.risk_level,
        "is_paid":   getattr(sess, "is_paid", False),
        "meet_link": getattr(sess, "meet_link", None),
        "therapist": (sess.assigned_therapist.full_name or sess.assigned_therapist.username)
                     if sess.assigned_therapist else None,
    })


# ─────────────────────────────────────────────────────────────────────────────
# SURVIVOR API — RETURN TO SESSION (Safe Name + PIN)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/survivor/return", methods=["POST"])
def survivor_return():
    data  = request.get_json(silent=True) or {}
    alias = data.get("alias", "").strip()
    pin   = data.get("pin",   "").strip()

    if not alias or not pin:
        return jsonify({"error": "Safe Name and PIN are required."}), 400

    pin_hashed = hash_pin(pin)

    sess = (SurvivorSession.query
            .filter_by(alias=alias, pin_hash=pin_hashed)
            .filter(SurvivorSession.status != "Blocked")
            .order_by(SurvivorSession.created_at.desc())
            .first())

    if not sess:
        return jsonify({"error": "No session found for that Safe Name and PIN."}), 404

    if sess.expires_at and datetime.utcnow() > sess.expires_at:
        return jsonify({"error": "Session expired. Please start a new session."}), 410

    if getattr(sess, "is_paid", False):
        return jsonify({"redirect": f"/survivor/chat/{sess.session_uuid}"})

    return jsonify({"redirect": f"/payment/plans/{sess.session_uuid}"})


# ─────────────────────────────────────────────────────────────────────────────
# SURVIVOR API — SAVE / UPDATE EMERGENCY DETAILS
# Data is stored but ONLY surfaced to emergency responders.
# Therapist templates deliberately never receive these fields.
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/survivor/emergency-details", methods=["POST"])
def save_emergency_details():
    data         = request.get_json(silent=True) or {}
    session_uuid = data.get("session_uuid", "").strip()

    if not session_uuid:
        return jsonify({"error": "session_uuid required"}), 400

    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first()
    if not sess:
        return jsonify({"error": "Session not found"}), 404

    sess.emergency_city       = data.get("emergency_city",       "")[:100]
    sess.emergency_age_range  = data.get("emergency_age_range",  "")[:20]
    sess.emergency_preference = data.get("emergency_preference", "")[:50]
    sess.emergency_contact    = data.get("emergency_contact",    "")[:20]
    sess.emergency_consent    = bool(data.get("emergency_consent", False))
    sess.emergency_submitted  = True
    db.session.commit()

    # Only broadcast to emergency room if this is a High-risk session
    if sess.risk_level == "High":
        socketio.emit("emergency_details_received", {
            "session_uuid": session_uuid,
            "alias":        sess.alias,
            "city":         sess.emergency_city,
            "age_range":    sess.emergency_age_range,
            "preference":   sess.emergency_preference,
            "has_contact":  bool(sess.emergency_contact),
        }, to="emergency_room")

    return jsonify({"success": True})


# ─────────────────────────────────────────────────────────────────────────────
# API — TEXT ANALYSIS
# Accepts emergency details inline so the analyse form collects them in
# one step (mandatory). Emergency data is stored for ALL survivors but only
# surfaced to emergency responders when risk_level == "High".
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/analyse", methods=["POST"])
def api_analyse():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required."}), 400

    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text field must not be empty."}), 400

    alias = (data.get("alias") or "Anonymous").strip()[:50]

    # Emergency safety details — collected upfront in the mandatory safety form
    emergency_city       = (data.get("emergency_city",       "") or "")[:100]
    emergency_age_range  = (data.get("emergency_age_range",  "") or "")[:20]
    emergency_preference = (data.get("emergency_preference", "") or "")[:50]
    emergency_contact    = (data.get("emergency_contact",    "") or "")[:20]
    emergency_consent    = bool(data.get("emergency_consent", False))

    try:
        emotion_scores = emotion_model.predict(text)
        result = severity_engine.analyse(emotion_scores)
    except Exception as e:
        print("AI ERROR:", e)
        return jsonify({"error": str(e)}), 500

    is_high = result["risk_level"] == "High"

    sess = SurvivorSession(
        alias                = alias,
        input_text           = text,
        emotion_scores       = json.dumps(emotion_scores),
        severity_score       = result["severity_score"],
        risk_level           = result["risk_level"],
        status               = "Escalated" if is_high else "Pending",
        is_paid              = False,
        emergency_city       = emergency_city,
        emergency_age_range  = emergency_age_range,
        emergency_preference = emergency_preference,
        emergency_contact    = emergency_contact,
        emergency_consent    = emergency_consent,
        emergency_submitted  = bool(emergency_city or emergency_age_range),
    )
    db.session.add(sess)
    db.session.commit()

    if is_high:
        esc = EscalationLog(
            session_id   = sess.id,
            escalated_by = "system",
            action_taken = "Auto-escalation — High risk detected",
        )
        db.session.add(esc)
        db.session.commit()

        # Notify emergency responders with the pre-collected safety details
        socketio.emit("new_high_risk", {
            "session_uuid": sess.session_uuid,
            "alias":        alias,
            "severity":     result["severity_score"],
            "city":         emergency_city,
            "age_range":    emergency_age_range,
            "preference":   emergency_preference,
            "has_contact":  bool(emergency_contact),
            "consent":      emergency_consent,
        }, to="emergency_room")

    if result["risk_level"] in ("Moderate", "High"):
        socketio.emit("new_session", {
            "session_uuid": sess.session_uuid,
            "risk_level":   result["risk_level"],
            "alias":        alias,
        }, to="therapist_room")

    return jsonify({
        "session_uuid":       sess.session_uuid,
        "transcribed_text":   text,
        "emotion_scores":     emotion_scores,
        "severity_score":     result["severity_score"],
        "risk_level":         result["risk_level"],
        "recommended_action": result.get("recommended_action", ""),
        "escalation_title":   result.get("escalation_title", result["risk_level"] + " Risk"),
        "escalation_color":   result.get("escalation_color", "#6b7280"),
        "escalation_icon":    result.get("escalation_icon", "📊"),
        "chat_enabled":       result["risk_level"] in ("Moderate", "High"),
        "payment_url":        f"/payment/plans/{sess.session_uuid}",
        "emergency_url":      f"/survivor/emergency/{sess.session_uuid}" if is_high else None,
    })


# ─────────────────────────────────────────────────────────────────────────────
# API — AUDIO ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/analyse-audio", methods=["POST"])
def api_analyse_audio():
    try:
        import speech_recognition as sr
    except ImportError:
        return jsonify({"error": "SpeechRecognition not installed. Run: pip install SpeechRecognition"}), 500
    try:
        from pydub import AudioSegment
    except ImportError:
        return jsonify({"error": "pydub not installed. Run: pip install pydub"}), 500

    if "audio" not in request.files:
        return jsonify({"error": "Multipart field 'audio' is required."}), 400

    audio_file      = request.files["audio"]
    original_suffix = os.path.splitext(audio_file.filename or "")[-1].lower() or ".webm"
    tmp_in_path     = None
    tmp_wav_path    = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_suffix) as tmp_in:
            audio_file.save(tmp_in.name)
            tmp_in_path = tmp_in.name

        tmp_wav_path = tmp_in_path.rsplit(".", 1)[0] + "_conv.wav"
        fmt = original_suffix.lstrip(".") or "webm"
        if fmt == "blob":
            fmt = "webm"
        audio_seg = AudioSegment.from_file(tmp_in_path, format=fmt)
        audio_seg = audio_seg.set_frame_rate(16000).set_channels(1)
        audio_seg.export(tmp_wav_path, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(tmp_wav_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data)

    except sr.UnknownValueError:
        return jsonify({"error": "Could not understand audio. Please speak clearly."}), 422
    except sr.RequestError as exc:
        return jsonify({"error": f"Speech service error: {exc}"}), 503
    except Exception as exc:
        return jsonify({"error": f"Audio processing failed: {str(exc)}"}), 500
    finally:
        for p in [tmp_in_path, tmp_wav_path]:
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass

    alias = (request.form.get("alias") or "Anonymous").strip()[:50]

    # Emergency details from multipart form fields
    emergency_city       = (request.form.get("emergency_city",       "") or "")[:100]
    emergency_age_range  = (request.form.get("emergency_age_range",  "") or "")[:20]
    emergency_preference = (request.form.get("emergency_preference", "") or "")[:50]
    emergency_contact    = (request.form.get("emergency_contact",    "") or "")[:20]
    emergency_consent    = request.form.get("emergency_consent", "false").lower() == "true"

    try:
        emotion_scores = emotion_model.predict(text)
        result         = severity_engine.analyse(emotion_scores)
    except Exception as e:
        return jsonify({"error": f"AI analysis failed: {str(e)}"}), 500

    is_high = result["risk_level"] == "High"

    sess = SurvivorSession(
        alias                = alias,
        input_text           = text,
        emotion_scores       = json.dumps(emotion_scores),
        severity_score       = result["severity_score"],
        risk_level           = result["risk_level"],
        status               = "Escalated" if is_high else "Pending",
        is_paid              = False,
        emergency_city       = emergency_city,
        emergency_age_range  = emergency_age_range,
        emergency_preference = emergency_preference,
        emergency_contact    = emergency_contact,
        emergency_consent    = emergency_consent,
        emergency_submitted  = bool(emergency_city or emergency_age_range),
    )
    db.session.add(sess)
    db.session.commit()

    if is_high:
        esc = EscalationLog(
            session_id   = sess.id,
            escalated_by = "system",
            action_taken = "Auto-escalation — High risk (audio session)",
        )
        db.session.add(esc)
        db.session.commit()

        socketio.emit("new_high_risk", {
            "session_uuid": sess.session_uuid,
            "alias":        alias,
            "severity":     result["severity_score"],
            "city":         emergency_city,
            "age_range":    emergency_age_range,
            "preference":   emergency_preference,
            "has_contact":  bool(emergency_contact),
            "consent":      emergency_consent,
        }, to="emergency_room")

    if result["risk_level"] in ("Moderate", "High"):
        socketio.emit("new_session", {
            "session_uuid": sess.session_uuid,
            "risk_level":   result["risk_level"],
            "alias":        alias,
        }, to="therapist_room")

    return jsonify({
        "session_uuid":       sess.session_uuid,
        "transcribed_text":   text,
        "emotion_scores":     emotion_scores,
        "severity_score":     result["severity_score"],
        "risk_level":         result["risk_level"],
        "recommended_action": result.get("recommended_action", ""),
        "escalation_title":   result.get("escalation_title", result["risk_level"] + " Risk"),
        "escalation_color":   result.get("escalation_color", "#6b7280"),
        "escalation_icon":    result.get("escalation_icon", "📊"),
        "chat_enabled":       result["risk_level"] in ("Moderate", "High"),
        "payment_url":        f"/payment/plans/{sess.session_uuid}",
        "emergency_url":      f"/survivor/emergency/{sess.session_uuid}" if is_high else None,
    })


# ─────────────────────────────────────────────────────────────────────────────
# THERAPIST ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/therapist")
@role_required("therapist")
def therapist_dashboard():
    my_sessions = SurvivorSession.query.filter_by(
        therapist_id=current_user.id
    ).order_by(SurvivorSession.created_at.desc()).all()

    pending = SurvivorSession.query.filter_by(
        status="Pending", therapist_id=None
    ).order_by(SurvivorSession.created_at.desc()).all()

    high_risk = SurvivorSession.query.filter_by(
        risk_level="High"
    ).order_by(SurvivorSession.created_at.desc()).limit(10).all()

    return render_template("therapist/dashboard.html",
                           my_sessions=my_sessions,
                           pending=pending,
                           high_risk=high_risk)


@app.route("/therapist/session/<session_uuid>")
@role_required("therapist")
def therapist_session(session_uuid):
    sess         = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    messages     = ChatMessage.query.filter_by(
        session_id=sess.id
    ).order_by(ChatMessage.timestamp.asc()).all()
    emotion_data = json.loads(sess.emotion_scores) if sess.emotion_scores else {}
    # NOTE: Emergency details are deliberately NOT passed to the therapist template.
    return render_template("therapist/session.html",
                           session=sess,
                           messages=messages,
                           emotion_data=emotion_data)


@app.route("/api/therapist/accept/<session_uuid>", methods=["POST"])
@role_required("therapist")
def accept_session(session_uuid):
    data              = request.get_json(silent=True) or {}
    sess              = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    sess.therapist_id = current_user.id
    sess.status       = "Assigned"

    meet_link = data.get("meet_link", "").strip()
    if meet_link:
        sess.meet_link = meet_link

    db.session.commit()
    log_action("accept_session", f"Session {session_uuid}")

    socketio.emit("session_accepted", {
        "session_uuid":   session_uuid,
        "therapist_name": current_user.full_name or current_user.username,
        "meet_link":      getattr(sess, "meet_link", "") or "",
    }, to=session_uuid)

    socketio.emit("session_accepted_dashboard", {
        "session_uuid": session_uuid,
    }, to="therapist_room")

    return jsonify({
        "success":   True,
        "chat_url":  f"/therapist/session/{session_uuid}",
        "meet_link": getattr(sess, "meet_link", "") or "",
    })


@app.route("/api/therapist/set-meet-link/<session_uuid>", methods=["POST"])
@role_required("therapist")
def set_meet_link(session_uuid):
    data      = request.get_json(silent=True) or {}
    meet_link = data.get("meet_link", "").strip()

    if not meet_link:
        return jsonify({"error": "meet_link is required."}), 400

    sess           = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    sess.meet_link = meet_link
    db.session.commit()

    msg_text = "🎥 Your therapist has started a video session. Join here:\n" + meet_link
    msg = ChatMessage(
        session_id     = sess.id,
        sender_role    = "therapist",
        sender_user_id = current_user.id,
        message        = msg_text,
    )
    db.session.add(msg)
    db.session.commit()

    socketio.emit("receive_message", {
        "message":     msg_text,
        "sender_role": "therapist",
        "timestamp":   msg.timestamp.strftime("%H:%M"),
    }, to=session_uuid)

    sessions_held = ChatMessage.query.filter_by(
        session_id  = sess.id,
        sender_role = "therapist",
    ).count()

    return jsonify({"success": True, "sessions_held": sessions_held})


@app.route("/api/therapist/resolve/<session_uuid>", methods=["POST"])
@role_required("therapist")
def resolve_session(session_uuid):
    data             = request.get_json(silent=True) or {}
    sess             = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    sess.status      = "Resolved"
    sess.notes       = data.get("notes", "")
    sess.resolved_at = datetime.utcnow()
    db.session.commit()
    log_action("resolve_session", f"Session {session_uuid}")

    socketio.emit("session_resolved", {
        "message": "Your session has been marked as resolved by your therapist."
    }, to=session_uuid)

    return jsonify({"success": True})


@app.route("/api/therapist/sessions")
@role_required("therapist")
def therapist_sessions_api():
    sessions = SurvivorSession.query.filter_by(
        therapist_id=current_user.id
    ).order_by(SurvivorSession.created_at.desc()).all()
    return jsonify([{
        "uuid":       s.session_uuid,
        "alias":      s.alias,
        "risk_level": s.risk_level,
        "status":     s.status,
        "created_at": s.created_at.isoformat(),
        "severity":   s.severity_score,
    } for s in sessions])


# ─────────────────────────────────────────────────────────────────────────────
# THERAPIST SLOT MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/therapist/slots")
@role_required("therapist")
def therapist_slots():
    from models import TherapistSlot
    from datetime import date
    slots = TherapistSlot.query.filter_by(
        therapist_id=current_user.id
    ).filter(TherapistSlot.slot_date >= date.today()).order_by(
        TherapistSlot.slot_date, TherapistSlot.slot_time
    ).all()
    return render_template("therapist/slots.html", slots=slots, today=date.today().isoformat())


@app.route("/api/therapist/slots/add", methods=["POST"])
@role_required("therapist")
def add_slot():
    from models import TherapistSlot
    from datetime import date as dt_date
    data          = request.get_json(silent=True) or {}
    slot_date_str = data.get("slot_date", "")
    slot_time     = data.get("slot_time", "")
    duration      = int(data.get("duration_min", 45))

    if not slot_date_str or not slot_time:
        return jsonify({"error": "slot_date and slot_time required"}), 400

    try:
        slot_date = dt_date.fromisoformat(slot_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    existing = TherapistSlot.query.filter_by(
        therapist_id=current_user.id,
        slot_date=slot_date,
        slot_time=slot_time
    ).first()
    if existing:
        return jsonify({"error": "Slot already exists at this time"}), 409

    slot = TherapistSlot(
        therapist_id=current_user.id,
        slot_date=slot_date,
        slot_time=slot_time,
        duration_min=duration,
    )
    db.session.add(slot)
    db.session.commit()
    log_action("add_slot", f"{slot_date_str} {slot_time}")
    return jsonify({"success": True, "slot_id": slot.id})


@app.route("/api/therapist/slots/delete/<int:slot_id>", methods=["POST"])
@role_required("therapist")
def delete_slot(slot_id):
    from models import TherapistSlot
    slot = TherapistSlot.query.filter_by(id=slot_id, therapist_id=current_user.id).first_or_404()
    if slot.is_booked:
        return jsonify({"error": "Cannot delete a booked slot"}), 400
    db.session.delete(slot)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/slots/available")
def available_slots():
    from models import TherapistSlot
    from datetime import date, timedelta
    therapist_id = request.args.get("therapist_id", type=int)
    days_ahead   = int(request.args.get("days", 14))

    today    = date.today()
    end_date = today + timedelta(days=days_ahead)

    q = TherapistSlot.query.filter(
        TherapistSlot.is_booked == False,
        TherapistSlot.slot_date >= today,
        TherapistSlot.slot_date <= end_date,
    )
    if therapist_id:
        q = q.filter(TherapistSlot.therapist_id == therapist_id)

    slots = q.order_by(TherapistSlot.slot_date, TherapistSlot.slot_time).all()

    return jsonify([{
        "id":           s.id,
        "therapist_id": s.therapist_id,
        "therapist":    s.therapist.full_name or s.therapist.username,
        "date":         s.slot_date.isoformat(),
        "time":         s.slot_time,
        "duration_min": s.duration_min,
        "display":      f"{s.slot_date.strftime('%a, %d %b')} at {s.slot_time}",
    } for s in slots])


@app.route("/api/slots/book/<int:slot_id>", methods=["POST"])
def book_slot(slot_id):
    from models import TherapistSlot
    data         = request.get_json(silent=True) or {}
    session_uuid = data.get("session_uuid", "")

    slot = TherapistSlot.query.get(slot_id)
    if not slot:
        return jsonify({"error": "Slot not found"}), 404
    if slot.is_booked:
        return jsonify({"error": "This slot is already taken. Please choose another."}), 409

    slot.is_booked = True
    slot.booked_by = session_uuid
    db.session.commit()

    socketio.emit("slot_booked", {
        "slot_id":      slot_id,
        "date":         slot.slot_date.isoformat(),
        "time":         slot.slot_time,
        "session_uuid": session_uuid,
    }, to="therapist_room")

    return jsonify({"success": True, "date": slot.slot_date.isoformat(), "time": slot.slot_time})


# ─────────────────────────────────────────────────────────────────────────────
# EMERGENCY ROUTES  (role=emergency only)
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/emergency")
@role_required("emergency")
def emergency_dashboard():
    escalated = SurvivorSession.query.filter_by(
        status="Escalated"
    ).order_by(SurvivorSession.created_at.desc()).all()

    high_risk = SurvivorSession.query.filter_by(
        risk_level="High"
    ).order_by(SurvivorSession.created_at.desc()).limit(20).all()

    return render_template("emergency/dashboard.html",
                           escalated=escalated,
                           high_risk=high_risk)


@app.route("/emergency/session/<session_uuid>")
@role_required("emergency")
def emergency_session_detail(session_uuid):
    """
    Full session detail including emergency contact info.
    ONLY accessible to emergency role — never to therapists or admins.
    """
    sess = SurvivorSession.query.filter_by(
        session_uuid=session_uuid,
        risk_level="High"
    ).first_or_404()
    return render_template("emergency/session_detail.html", session=sess)


@app.route("/api/emergency/respond/<session_uuid>", methods=["POST"])
@role_required("emergency")
def emergency_respond(session_uuid):
    data = request.get_json(silent=True) or {}
    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    esc  = EscalationLog(
        session_id   = sess.id,
        escalated_by = current_user.username,
        action_taken = data.get("action", "Responder engaged"),
        responder_id = current_user.id,
    )
    sess.status = "Escalated-Responded"
    db.session.add(esc)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/emergency/details/<session_uuid>")
@role_required("emergency")
def get_emergency_details(session_uuid):
    """
    Returns full emergency details for a High-risk session.
    Strictly gated to emergency role. Contact shown only if consent given.
    """
    sess = SurvivorSession.query.filter_by(
        session_uuid=session_uuid,
        risk_level="High"
    ).first()

    if not sess:
        return jsonify({"error": "High-risk session not found"}), 404

    return jsonify({
        "session_uuid":       sess.session_uuid,
        "alias":              sess.alias,
        "severity_score":     sess.severity_score,
        "city":               sess.emergency_city       or "Not provided",
        "age_range":          sess.emergency_age_range  or "Not provided",
        "preferred_response": sess.emergency_preference or "Not provided",
        "contact_provided":   bool(sess.emergency_contact),
        # Contact number only shown if the survivor explicitly consented
        "contact":            sess.emergency_contact if sess.emergency_consent else "Consent not given",
        "consent":            sess.emergency_consent,
        "submitted_at":       sess.created_at.isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    users     = User.query.order_by(User.created_at.desc()).all()
    sessions  = SurvivorSession.query.order_by(
        SurvivorSession.created_at.desc()).limit(50).all()
    total_s   = SurvivorSession.query.count()
    high_c    = SurvivorSession.query.filter_by(risk_level="High").count()
    pending_t = User.query.filter_by(role="therapist", is_approved=False).count()
    audit     = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(30).all()
    return render_template("admin/dashboard.html",
                           users=users, sessions=sessions, audit=audit,
                           stats={"total": total_s, "high": high_c,
                                  "pending_therapists": pending_t})


@app.route("/api/admin/approve/<int:user_id>", methods=["POST"])
@role_required("admin")
def approve_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    user.is_approved = True
    db.session.commit()
    log_action("approve_user", f"Approved {user.username} ({user.role})")
    return jsonify({"success": True})


@app.route("/api/admin/disable/<int:user_id>", methods=["POST"])
@role_required("admin")
def disable_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    user.is_active = False
    db.session.commit()
    log_action("disable_user", f"Disabled {user.username}")
    return jsonify({"success": True})


@app.route("/api/admin/stats")
@role_required("admin")
def admin_stats():
    from sqlalchemy import func
    rows = db.session.query(
        SurvivorSession.risk_level,
        func.count(SurvivorSession.id)
    ).group_by(SurvivorSession.risk_level).all()
    return jsonify({"risk_distribution": dict(rows)})


# ─────────────────────────────────────────────────────────────────────────────
# SOCKETIO — REAL-TIME CHAT
# ─────────────────────────────────────────────────────────────────────────────
@socketio.on("join")
def on_join(data):
    room = data.get("room", "")
    if room:
        join_room(room)
        emit("status", {"msg": f"Connected to room {room}"})


@socketio.on("leave")
def on_leave(data):
    room = data.get("room", "")
    if room:
        leave_room(room)


@socketio.on("send_message")
def handle_message(data):
    room         = data.get("room", "")
    message_text = (data.get("message") or "").strip()
    sender_role  = data.get("sender_role", "survivor")
    is_voice     = bool(data.get("is_voice", False))

    if not message_text or not room:
        return

    sess = SurvivorSession.query.filter_by(session_uuid=room).first()
    if not sess:
        return

    sender_user_id = None
    if sender_role != "survivor" and current_user.is_authenticated:
        sender_user_id = current_user.id

    msg = ChatMessage(
        session_id     = sess.id,
        sender_role    = sender_role,
        sender_user_id = sender_user_id,
        message        = message_text,
        is_voice       = is_voice,
    )
    db.session.add(msg)
    db.session.commit()

    emit("receive_message", {
        "message":     message_text,
        "sender_role": sender_role,
        "timestamp":   msg.timestamp.strftime("%H:%M"),
        "is_voice":    is_voice,
    }, room=room)


@socketio.on("join_therapist_room")
def join_therapist_room():
    join_room("therapist_room")


@socketio.on("join_emergency_room")
def join_emergency_room():
    join_room("emergency_room")


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE INIT + MIGRATIONS + ADMIN SEED
# ─────────────────────────────────────────────────────────────────────────────
def init_db():
    with app.app_context():
        from payment_models import Payment, PaymentPlan, Subscription
        db.create_all()

        from sqlalchemy import text
        migrations = [
            # survivor_sessions
            "ALTER TABLE survivor_sessions ADD COLUMN is_paid BOOLEAN DEFAULT 0",
            "ALTER TABLE survivor_sessions ADD COLUMN resolved_at DATETIME",
            "ALTER TABLE survivor_sessions ADD COLUMN notes TEXT",
            "ALTER TABLE survivor_sessions ADD COLUMN meet_link VARCHAR(300)",
            "ALTER TABLE survivor_sessions ADD COLUMN meet_requested BOOLEAN DEFAULT 0",
            "ALTER TABLE survivor_sessions ADD COLUMN safe_name_hash VARCHAR(64)",
            "ALTER TABLE survivor_sessions ADD COLUMN emergency_city VARCHAR(100)",
            "ALTER TABLE survivor_sessions ADD COLUMN emergency_age_range VARCHAR(20)",
            "ALTER TABLE survivor_sessions ADD COLUMN emergency_contact VARCHAR(20)",
            "ALTER TABLE survivor_sessions ADD COLUMN emergency_preference VARCHAR(50)",
            "ALTER TABLE survivor_sessions ADD COLUMN emergency_consent BOOLEAN DEFAULT 0",
            "ALTER TABLE survivor_sessions ADD COLUMN emergency_submitted BOOLEAN DEFAULT 0",
            # users
            "ALTER TABLE users ADD COLUMN reset_token VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN reset_expires DATETIME",
        ]

        try:
            from models import TherapistSlot
        except ImportError:
            pass

        with db.engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    pass  # column already exists — safe to ignore

        if not User.query.filter_by(role="admin").first():
            admin = User(
                username      = "admin",
                email         = "admin@safevoice.org",
                password_hash = generate_password_hash("Admin@123"),
                role          = "admin",
                full_name     = "Platform Administrator",
                is_approved   = True,
                is_active     = True,
            )
            db.session.add(admin)
            db.session.commit()
            print("[DB] Admin account created  ->  admin@safevoice.org / Admin@123")

        print("[DB] Database ready.")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("\n" + "=" * 55)
    print("  SafeVoice is running!")
    print("  Open your browser -> http://localhost:5000")
    print("  Admin login       -> admin@safevoice.org / Admin@123")
    print("  Press CTRL+C to stop the server")
    print("=" * 55 + "\n")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
