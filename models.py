# models.py — SafeVoice Database Models
# Survivors are fully anonymous — no real names, no emails, no accounts.
# Safe Name = nature alias + PIN hash (zero identity, full accountability).

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()


# ─────────────────────────────────────────────────────────────────────────────
# USERS — Therapists, Admins, Emergency Responders
# ─────────────────────────────────────────────────────────────────────────────
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(80),  unique=True, nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    password_hash  = db.Column(db.String(256), nullable=False)
    role           = db.Column(db.String(20),  nullable=False)
    full_name      = db.Column(db.String(120))
    is_active      = db.Column(db.Boolean, default=True)
    is_approved    = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    specialization = db.Column(db.String(200))
    bio            = db.Column(db.Text)
    reset_token    = db.Column(db.String(100), nullable=True)     # ← password reset
    reset_expires  = db.Column(db.DateTime,    nullable=True)

    sessions      = db.relationship("SurvivorSession", backref="assigned_therapist",
                                    lazy=True, foreign_keys="SurvivorSession.therapist_id")
    messages_sent = db.relationship("ChatMessage", backref="sender_user",
                                    lazy=True, foreign_keys="ChatMessage.sender_user_id")


# ─────────────────────────────────────────────────────────────────────────────
# SURVIVOR SESSION — fully anonymous
# ─────────────────────────────────────────────────────────────────────────────
class SurvivorSession(db.Model):
    __tablename__ = "survivor_sessions"

    id             = db.Column(db.Integer, primary_key=True)
    session_uuid   = db.Column(db.String(36), unique=True,
                                default=lambda: str(uuid.uuid4()))

    # ── Safe Name System ───────────────────────────────────────────────────
    # Survivor picks a nature-based alias (e.g. "Blue Lotus") — no real name.
    # They also set a 4-digit PIN stored as SHA-256 hash.
    # Together this lets them RETURN to their session without any account.
    alias          = db.Column(db.String(80))        # e.g. "Blue Lotus"
    safe_name_hash = db.Column(db.String(64))        # SHA-256 of alias+PIN
    pin_hash       = db.Column(db.String(64))        # SHA-256 of PIN alone

    input_text     = db.Column(db.Text, nullable=False)
    emotion_scores = db.Column(db.Text)
    severity_score = db.Column(db.Float)
    risk_level     = db.Column(db.String(20))        # Low | Moderate | High
    status         = db.Column(db.String(30), default="Pending")

    therapist_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at    = db.Column(db.DateTime, nullable=True)
    notes          = db.Column(db.Text)
    expires_at     = db.Column(db.DateTime, nullable=True)

    # Payment
    is_paid        = db.Column(db.Boolean, default=False)

    # Meet / Video
    meet_link      = db.Column(db.String(300), nullable=True)
    meet_requested = db.Column(db.Boolean, default=False)

    # Abuse prevention
    is_flagged     = db.Column(db.Boolean, default=False)
    flag_reason    = db.Column(db.Text, nullable=True)

    # ── Emergency Details (High Risk only) ────────────────────────────────
    # Collected ONLY when severity = High. Stored encrypted-at-rest.
    # Used ONLY by emergency responder if survivor consents.
    # Fields: city, age_range, safe_contact (optional phone/WhatsApp),
    #         emergency_preference, consent_given
    emergency_city        = db.Column(db.String(100), nullable=True)
    emergency_age_range   = db.Column(db.String(20),  nullable=True)  # e.g. "18-25"
    emergency_contact     = db.Column(db.String(20),  nullable=True)  # optional phone
    emergency_preference  = db.Column(db.String(50),  nullable=True)  # police|helpline|ambulance
    emergency_consent     = db.Column(db.Boolean, default=False)
    emergency_submitted   = db.Column(db.Boolean, default=False)

    chat_messages  = db.relationship("ChatMessage", backref="session", lazy=True)


# ─────────────────────────────────────────────────────────────────────────────
# CHAT MESSAGE
# ─────────────────────────────────────────────────────────────────────────────
class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id             = db.Column(db.Integer, primary_key=True)
    session_id     = db.Column(db.Integer, db.ForeignKey("survivor_sessions.id"), nullable=False)
    sender_role    = db.Column(db.String(20), nullable=False)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    message        = db.Column(db.Text, nullable=False)
    timestamp      = db.Column(db.DateTime, default=datetime.utcnow)
    is_voice       = db.Column(db.Boolean, default=False)


# ─────────────────────────────────────────────────────────────────────────────
# ESCALATION LOG
# ─────────────────────────────────────────────────────────────────────────────
class EscalationLog(db.Model):
    __tablename__ = "escalation_logs"

    id           = db.Column(db.Integer, primary_key=True)
    session_id   = db.Column(db.Integer, db.ForeignKey("survivor_sessions.id"), nullable=False)
    escalated_by = db.Column(db.String(30))
    action_taken = db.Column(db.Text)
    responder_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    timestamp    = db.Column(db.DateTime, default=datetime.utcnow)
    session_ref  = db.relationship("SurvivorSession", backref="escalations")


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id         = db.Column(db.Integer, primary_key=True)
    actor_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action     = db.Column(db.String(200), nullable=False)
    details    = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow)