# payment_models.py
from models import db
from datetime import datetime
import uuid


class PaymentPlan(db.Model):
    __tablename__ = "payment_plans"
    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(80), nullable=False)
    plan_type        = db.Column(db.String(20), nullable=False)   # per_session | subscription
    price_paise      = db.Column(db.Integer,    nullable=False)   # ₹1 = 100 paise
    sessions         = db.Column(db.Integer, default=1)
    validity_days    = db.Column(db.Integer, default=1)
    description      = db.Column(db.Text)
    is_active        = db.Column(db.Boolean, default=True)
    razorpay_plan_id = db.Column(db.String(100))
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def price_rupees(self):
        return self.price_paise / 100


class Payment(db.Model):
    __tablename__ = "payments"
    id                  = db.Column(db.Integer, primary_key=True)
    payment_ref         = db.Column(db.String(36), unique=True,
                                     default=lambda: str(uuid.uuid4()))
    session_uuid        = db.Column(db.String(36), nullable=False)
    plan_id             = db.Column(db.Integer, db.ForeignKey("payment_plans.id"))
    amount_paise        = db.Column(db.Integer, nullable=False)
    currency            = db.Column(db.String(5), default="INR")
    status              = db.Column(db.String(20), default="created")
    razorpay_order_id   = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    razorpay_signature  = db.Column(db.String(256))
    therapist_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at             = db.Column(db.DateTime, nullable=True)

    plan      = db.relationship("PaymentPlan", backref="payments")
    therapist = db.relationship("User", foreign_keys=[therapist_id], backref="payments")  # ← ADDED


class Subscription(db.Model):
    __tablename__ = "subscriptions"
    id                       = db.Column(db.Integer, primary_key=True)
    session_uuid             = db.Column(db.String(36), nullable=False)
    plan_id                  = db.Column(db.Integer, db.ForeignKey("payment_plans.id"))
    razorpay_subscription_id = db.Column(db.String(100))
    status                   = db.Column(db.String(20), default="created")
    sessions_remaining       = db.Column(db.Integer, default=0)
    start_date               = db.Column(db.DateTime, nullable=True)
    end_date                 = db.Column(db.DateTime, nullable=True)
    created_at               = db.Column(db.DateTime, default=datetime.utcnow)

    plan = db.relationship("PaymentPlan", backref="subscriptions")