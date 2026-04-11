# emotion_model.py
# Wraps HuggingFace emotion classifier.
# Set MOCK_AI=true in .env to skip model download entirely (great for demos).

import os

_classifier = None
_MOCK_MODE  = os.environ.get("MOCK_AI", "false").lower() == "true"

def _load():
    global _classifier, _MOCK_MODE
    if _MOCK_MODE:
        print("[emotion_model] MOCK_AI=true — skipping model download, using smart keyword scoring.")
        return
    try:
        from transformers import pipeline
        print("[emotion_model] Loading AI model... (first run downloads ~270MB, please wait)")
        _classifier = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            return_all_scores=True,
            device=-1,   # CPU only
        )
        print("[emotion_model] AI model ready.")
    except Exception as e:
        print(f"[emotion_model] WARNING: Could not load AI model ({e})")
        print("[emotion_model] Falling back to smart keyword scoring.")
        _MOCK_MODE = True

_load()


def predict(text: str) -> dict:
    """Return emotion scores as {label: probability}."""
    if _MOCK_MODE or _classifier is None:
        return _mock_predict(text)
    try:
        raw = _classifier(text)[0]
        return {item["label"].lower(): round(item["score"], 4) for item in raw}
    except Exception:
        return _mock_predict(text)


def _mock_predict(text: str) -> dict:
    """
    Smart keyword-based scoring when the AI model is not available.
    Good enough for demos and development.
    """
    t = text.lower()

    fear_words    = ["scared","terrified","afraid","fear","nightmare","panic","helpless",
                     "trapped","danger","threat","hurt","unsafe","violent","attack"]
    sadness_words = ["sad","hopeless","cry","alone","empty","lost","depressed","broken",
                     "worthless","meaningless","grief","numb","exhausted","invisible"]
    anger_words   = ["angry","furious","hate","rage","disgusted","unfair","betrayed",
                     "lied","cheated","abused","harassed","humiliated"]
    joy_words     = ["happy","better","hopeful","grateful","smile","relieved","safe",
                     "loved","supported","okay","fine","good","thank"]

    def score(words):
        hits = sum(1 for w in words if w in t)
        return min(0.85, 0.10 + hits * 0.15)

    fear    = score(fear_words)
    sadness = score(sadness_words)
    anger   = score(anger_words)
    joy     = score(joy_words)
    neutral = 0.08
    disgust = 0.05
    surprise= 0.04

    total = fear + sadness + anger + joy + neutral + disgust + surprise
    return {
        "fear":     round(fear    / total, 4),
        "sadness":  round(sadness / total, 4),
        "anger":    round(anger   / total, 4),
        "joy":      round(joy     / total, 4),
        "neutral":  round(neutral / total, 4),
        "disgust":  round(disgust / total, 4),
        "surprise": round(surprise/ total, 4),
    }