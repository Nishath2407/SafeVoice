# payments.py
# Razorpay integration — order creation, webhook verification, receipt generation

import os, hmac, hashlib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template
import razorpay

from models import db, User, SurvivorSession
from payment_models import Payment, PaymentPlan, Subscription

payments_bp = Blueprint("payments", __name__, url_prefix="/payment")


# ─────────────────────────────────────────────
# Razorpay client
# ─────────────────────────────────────────────
def get_razorpay_client():
    key_id     = os.environ.get("RAZORPAY_KEY_ID",     "rzp_test_XXXXXXXXXXXX")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "your_test_secret_here")
    return razorpay.Client(auth=(key_id, key_secret))


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "your_test_secret_here")
    msg        = f"{order_id}|{payment_id}"
    generated  = hmac.new(
        key_secret.encode(), msg.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated, signature)


def get_available_therapists():
    therapists = User.query.filter_by(role="therapist", is_approved=True, is_active=True).all()
    result = []
    for t in therapists:
        active_count = SurvivorSession.query.filter_by(
            therapist_id=t.id, status="Assigned"
        ).count()
        result.append({
            "id":              t.id,
            "name":            t.full_name or t.username,
            "specialization":  t.specialization or "General Counselling",
            "bio":             t.bio or "Experienced counsellor.",
            "active_sessions": active_count,
            "available":       active_count < 5,
        })
    return result


def assign_therapist(session_uuid: str, therapist_id=None):
    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first()
    if not sess:
        return None

    if therapist_id:
        therapist = User.query.filter_by(id=therapist_id, role="therapist",
                                         is_approved=True, is_active=True).first()
    else:
        therapists = User.query.filter_by(role="therapist",
                                          is_approved=True, is_active=True).all()
        if not therapists:
            return None
        therapist = min(
            therapists,
            key=lambda t: SurvivorSession.query.filter_by(
                therapist_id=t.id, status="Assigned").count(),
            default=None
        )

    if therapist:
        sess.therapist_id = therapist.id
        sess.status = "Assigned"
        db.session.commit()

    return therapist


# ─────────────────────────────────────────────
# PLAN LISTING PAGE
# ─────────────────────────────────────────────
@payments_bp.route("/plans/<session_uuid>")
def plans(session_uuid):
    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()

    if PaymentPlan.query.count() == 0:
        _seed_plans()

    all_plans    = PaymentPlan.query.filter_by(is_active=True).all()
    therapists   = get_available_therapists()
    razorpay_key = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_XXXXXXXXXXXX")

    return render_template("payments/plan.html",
                           session=sess,
                           plans=all_plans,
                           therapists=therapists,
                           razorpay_key=razorpay_key)


# ─────────────────────────────────────────────
# CREATE ORDER (one-time payment)
# ─────────────────────────────────────────────
@payments_bp.route("/create-order", methods=["POST"])
def create_order():
    data         = request.get_json(silent=True) or {}
    session_uuid = data.get("session_uuid")
    plan_id      = data.get("plan_id")
    therapist_id = data.get("therapist_id")

    if not session_uuid or not plan_id:
        return jsonify({"error": "session_uuid and plan_id are required."}), 400

    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first()
    if not sess:
        return jsonify({"error": "Session not found."}), 404

    plan = db.session.get(PaymentPlan, plan_id)
    if not plan or not plan.is_active:
        return jsonify({"error": "Plan not found or inactive."}), 404

    client     = get_razorpay_client()
    order_data = {
        "amount":   plan.price_paise,
        "currency": "INR",
        "receipt":  f"sv_{session_uuid[:8]}_{plan_id}",
        "notes": {
            "session_uuid": session_uuid,
            "plan_name":    plan.name,
            "therapist_id": str(therapist_id or "auto"),
        }
    }

    try:
        rz_order = client.order.create(data=order_data)
    except Exception as e:
        return jsonify({"error": f"Razorpay error: {str(e)}"}), 502

    payment = Payment(
        session_uuid      = session_uuid,
        plan_id           = plan_id,
        amount_paise      = plan.price_paise,
        razorpay_order_id = rz_order["id"],
        therapist_id      = therapist_id,
        status            = "created",
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({
        "order_id":    rz_order["id"],
        "amount":      plan.price_paise,
        "currency":    "INR",
        "key_id":      os.environ.get("RAZORPAY_KEY_ID", "rzp_test_XXXXXXXXXXXX"),
        "plan_name":   plan.name,
        "payment_ref": payment.payment_ref,
    })


# ─────────────────────────────────────────────
# CREATE SUBSCRIPTION
# ─────────────────────────────────────────────
@payments_bp.route("/create-subscription", methods=["POST"])
def create_subscription():
    data         = request.get_json(silent=True) or {}
    session_uuid = data.get("session_uuid")
    plan_id      = data.get("plan_id")

    plan = db.session.get(PaymentPlan, plan_id)
    if not plan or plan.plan_type != "subscription":
        return jsonify({"error": "Not a subscription plan."}), 400

    if not plan.razorpay_plan_id:
        return jsonify({"error": "Razorpay plan ID not configured for this plan."}), 400

    client = get_razorpay_client()

    try:
        sub = client.subscription.create({
            "plan_id":         plan.razorpay_plan_id,
            "total_count":     52,
            "quantity":        1,
            "customer_notify": 0,
            "notes":           {"session_uuid": session_uuid},
        })
    except Exception as e:
        return jsonify({"error": f"Subscription error: {str(e)}"}), 502

    subscription = Subscription(
        session_uuid             = session_uuid,
        plan_id                  = plan_id,
        razorpay_subscription_id = sub["id"],
        sessions_remaining       = plan.sessions,
        status                   = "created",
    )
    db.session.add(subscription)
    db.session.commit()

    return jsonify({
        "subscription_id": sub["id"],
        "key_id":          os.environ.get("RAZORPAY_KEY_ID", "rzp_test_XXXXXXXXXXXX"),
        "plan_name":       plan.name,
    })


# ─────────────────────────────────────────────
# VERIFY PAYMENT
# ─────────────────────────────────────────────
@payments_bp.route("/verify", methods=["POST"])
def verify_payment():
    data         = request.get_json(silent=True) or {}
    order_id     = data.get("razorpay_order_id", "")
    payment_id   = data.get("razorpay_payment_id", "")
    signature    = data.get("razorpay_signature", "")
    session_uuid = data.get("session_uuid")
    therapist_id = data.get("therapist_id")

    key_id       = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_XXXXXXXXXXXX")
    is_test_mode = key_id == "rzp_test_XXXXXXXXXXXX" or not key_id

    if not is_test_mode:
        if not verify_razorpay_signature(order_id, payment_id, signature):
            return jsonify({"error": "Payment verification failed. Signature mismatch."}), 400

    payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
    if payment:
        payment.razorpay_payment_id = payment_id
        payment.razorpay_signature  = signature
        payment.status              = "paid"
        payment.paid_at             = datetime.utcnow()
        if therapist_id and not payment.therapist_id:
            payment.therapist_id = therapist_id
        db.session.commit()

    therapist = assign_therapist(session_uuid, therapist_id)

    sess = SurvivorSession.query.filter_by(session_uuid=session_uuid).first()
    if sess:
        sess.is_paid = True
        sess.status  = "Assigned" if therapist else "Pending"
        db.session.commit()

    return jsonify({
        "success":        True,
        "session_uuid":   session_uuid,
        "chat_url":       f"/survivor/chat/{session_uuid}",
        "receipt_url":    f"/payment/receipt/{payment.payment_ref if payment else 'unknown'}",
        "therapist_name": (therapist.full_name or therapist.username) if therapist else "Being assigned…",
    })


# ─────────────────────────────────────────────
# RAZORPAY WEBHOOK
# ─────────────────────────────────────────────
@payments_bp.route("/webhook", methods=["POST"])
def webhook():
    webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    received_sig   = request.headers.get("X-Razorpay-Signature", "")
    body           = request.get_data()

    if webhook_secret:
        expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_sig):
            return jsonify({"error": "Invalid webhook signature"}), 400

    event      = request.get_json(silent=True) or {}
    event_type = event.get("event")

    if event_type == "payment.captured":
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        rz_payment_id  = payment_entity.get("id")
        order_id       = payment_entity.get("order_id")
        payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
        if payment and payment.status != "paid":
            payment.razorpay_payment_id = rz_payment_id
            payment.status  = "paid"
            payment.paid_at = datetime.utcnow()
            db.session.commit()
            therapist = assign_therapist(payment.session_uuid)
            sess = SurvivorSession.query.filter_by(session_uuid=payment.session_uuid).first()
            if sess:
                sess.is_paid = True
                sess.status  = "Assigned" if therapist else "Pending"
                db.session.commit()

    elif event_type == "subscription.activated":
        sub_entity = event.get("payload", {}).get("subscription", {}).get("entity", {})
        rz_sub_id  = sub_entity.get("id")
        sub = Subscription.query.filter_by(razorpay_subscription_id=rz_sub_id).first()
        if sub:
            plan       = db.session.get(PaymentPlan, sub.plan_id)
            sub.status     = "active"
            sub.start_date = datetime.utcnow()
            sub.end_date   = datetime.utcnow() + timedelta(days=plan.validity_days if plan else 30)
            db.session.commit()

    elif event_type == "subscription.cancelled":
        sub_entity = event.get("payload", {}).get("subscription", {}).get("entity", {})
        rz_sub_id  = sub_entity.get("id")
        sub = Subscription.query.filter_by(razorpay_subscription_id=rz_sub_id).first()
        if sub:
            sub.status = "cancelled"
            db.session.commit()

    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────
# RECEIPT PAGE
# ─────────────────────────────────────────────
@payments_bp.route("/receipt/<payment_ref>")
def receipt(payment_ref):
    payment   = Payment.query.filter_by(payment_ref=payment_ref).first_or_404()
    plan      = payment.plan
    sess      = SurvivorSession.query.filter_by(session_uuid=payment.session_uuid).first()
    therapist = payment.therapist
    return render_template("payments/receipt.html",
                           payment=payment, plan=plan,
                           session=sess, therapist=therapist)


# ─────────────────────────────────────────────
# SUCCESS PAGE
# ─────────────────────────────────────────────
@payments_bp.route("/success/<session_uuid>")
def success(session_uuid):
    sess    = SurvivorSession.query.filter_by(session_uuid=session_uuid).first_or_404()
    payment = Payment.query.filter_by(
        session_uuid=session_uuid, status="paid"
    ).order_by(Payment.paid_at.desc()).first()
    return render_template("payments/success.html", session=sess, payment=payment)


# ─────────────────────────────────────────────
# THERAPIST LIST API
# ─────────────────────────────────────────────
@payments_bp.route("/api/therapists")
def api_therapists():
    return jsonify(get_available_therapists())


# ─────────────────────────────────────────────
# SEED DEFAULT PLANS
# ─────────────────────────────────────────────
def _seed_plans():
    plans = [
        PaymentPlan(
            name          = "Single Session",
            plan_type     = "per_session",
            price_paise   = 49900,
            sessions      = 1,
            validity_days = 1,
            description   = "One anonymous therapy session with a licensed counsellor.",
        ),
        PaymentPlan(
            name          = "3-Session Pack",
            plan_type     = "per_session",
            price_paise   = 129900,
            sessions      = 3,
            validity_days = 30,
            description   = "3 anonymous sessions to be used within 30 days.",
        ),
        PaymentPlan(
            name          = "Weekly Care Plan",
            plan_type     = "subscription",
            price_paise   = 99900,
            sessions      = 3,
            validity_days = 7,
            description   = "3 sessions per week. Auto-renews weekly. Cancel anytime.",
        ),
        PaymentPlan(
            name          = "Monthly Healing Plan",
            plan_type     = "subscription",
            price_paise   = 299900,
            sessions      = 12,
            validity_days = 30,
            description   = "12 sessions per month. Priority therapist matching.",
        ),
    ]
    for p in plans:
        db.session.add(p)
    db.session.commit()
    print("[payments] Default plans seeded.")