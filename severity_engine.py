# severity_engine.py
# Converts raw emotion scores into severity score, risk level, and escalation response.

WEIGHTS = {"fear": 0.5, "sadness": 0.3, "anger": 0.2}

ESCALATION = {
    "Low": {
        "title":   "You're safe here. Let's breathe together.",
        "message": (
            "Your feelings are completely valid. Here are some gentle steps:\n"
            "• Try the 5-4-3-2-1 grounding technique — name 5 things you can see.\n"
            "• Write down what you are feeling without judgment.\n"
            "• Reach out to a trusted person in your life.\n"
            "• Practice slow deep breaths: inhale 4s, hold 4s, exhale 6s.\n"
            "• Remember: you deserve care and safety."
        ),
        "color": "#10b981",
        "icon":  "🌱",
    },
    "Moderate": {
        "title":   "You deserve professional support.",
        "message": (
            "What you are carrying is heavy, and you do not have to carry it alone.\n"
            "• Speaking with a therapist can help you process these feelings safely.\n"
            "• Our platform can connect you anonymously with a licensed therapist right now.\n"
            "• iCall (India): 9152987821\n"
            "• NIMHANS Helpline: 080-46110007\n"
            "• You can request a voice session — no face, no real name required."
        ),
        "color": "#f59e0b",
        "icon":  "💛",
    },
    "High": {
        "title":   "⚠️ Please reach out for immediate help.",
        "message": (
            "You are not alone — help is available RIGHT NOW.\n"
            "• RAINN (US): 1-800-656-4673\n"
            "• Crisis Text Line (US): Text HOME to 741741\n"
            "• iCall (India): 9152987821\n"
            "• Vandrevala Foundation (India): 1860-2662-345 (24×7)\n"
            "• Emergency: 112 (India) | 911 (US) | 999 (UK)\n"
            "An emergency responder on our platform has been automatically notified."
        ),
        "color": "#ef4444",
        "icon":  "🆘",
    },
}


def compute_severity(scores: dict) -> float:
    return round(sum(WEIGHTS[e] * scores.get(e, 0.0) for e in WEIGHTS), 4)


def classify_risk(score: float) -> str:
    if score < 0.4:
        return "Low"
    elif score <= 0.75:
        return "Moderate"
    return "High"


def analyse(emotion_scores: dict) -> dict:
    severity   = compute_severity(emotion_scores)
    risk_level = classify_risk(severity)
    esc        = ESCALATION[risk_level]
    return {
        "severity_score":     severity,
        "risk_level":         risk_level,
        "recommended_action": esc["message"],
        "escalation_title":   esc["title"],
        "escalation_color":   esc["color"],
        "escalation_icon":    esc["icon"],
    }