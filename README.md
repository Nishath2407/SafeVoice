# 🛡️ SafeVoice
### AI-Powered Anonymous Emotional Risk Detection Platform for Women

> *"Because your voice deserves to be heard — safely, anonymously, without fear."*

SafeVoice is a full-stack web platform that uses artificial intelligence to detect emotional distress in women facing harassment-related trauma, assess risk levels, and connect them with licensed therapists — completely anonymously, with integrated Razorpay payments and real-time voice chat.

---

## 📸 Platform Overview

| Portal | Who Uses It | Access |
|--------|-------------|--------|
| 🌸 Survivor Portal | Women seeking help | No login, fully anonymous |
| 💚 Therapist Portal | Licensed counsellors | Register + Admin approval |
| 🆘 Emergency Console | First responders | Register (auto-approved) |
| ⚙️ Admin Dashboard | Platform managers | Pre-seeded account |

---

## ✨ Key Features

### 🤖 AI Emotion Detection
- Uses `j-hartmann/emotion-english-distilroberta-base` (HuggingFace)
- Detects 7 emotions: **fear, sadness, anger, joy, neutral, disgust, surprise**
- Custom weighted severity score: `fear×0.5 + sadness×0.3 + anger×0.2`
- Three risk levels: **Low → Moderate → High**

### 🔒 Complete Anonymity
- No name, email, or phone required for survivors
- Every session gets a randomly generated UUID
- Therapists only see the alias chosen by the survivor
- No audio recordings stored — only transcribed text
- Nothing linked to any real identity

### 💬 Real-Time Anonymous Chat
- WebSocket-powered live chat via **Flask-SocketIO**
- Voice recording → transcription → emotion analysis
- Therapist quick-response chips for empathetic replies
- Separate rooms per session — fully isolated

### 💳 Razorpay Payment Integration
- One-time session payments + weekly/monthly subscriptions
- Therapist selection (manual or auto-assign)
- Server-side HMAC-SHA256 signature verification
- Webhook listener for payment events
- Printable anonymous receipt (no PII)
- Confetti success page 🎉

### 🚨 Intelligent Escalation
- **Low risk** → Self-help suggestions (grounding, journaling)
- **Moderate risk** → Therapist consultation + chat unlock
- **High risk** → Emergency helplines + automatic real-time alert to responders

### 👩‍⚕️ Therapist Features
- Session queue (Pending / Active / High Risk tabs)
- Full emotion profile visualization per survivor
- Quick empathy chips: "I hear you", "You're safe here", etc.
- Private clinical notes per session
- Mark session as resolved

### 🆘 Emergency Responder Features
- Live dashboard with real-time SocketIO alerts
- Escalated case management with action logging
- Built-in emergency helpline quick reference

### ⚙️ Admin Features
- Approve / disable therapist accounts
- Full audit log of all platform actions
- Platform analytics (total sessions, high-risk count, pending approvals)
- Complete user management table

---

## 🗂️ Project Structure

```
safevoice/
│
├── app.py                  ← Flask application, all routes, SocketIO
├── models.py               ← SQLAlchemy DB models (User, Session, Chat, Audit)
├── payment_models.py       ← Payment, PaymentPlan, Subscription models
├── payments.py             ← Razorpay Blueprint (orders, verify, webhook, receipt)
├── emotion_model.py        ← HuggingFace emotion classifier wrapper
├── severity_engine.py      ← Weighted severity + escalation logic
├── requirements.txt        ← All Python dependencies
├── .env.example            ← Environment variable template
│
└── templates/
    ├── base.html                    ← Shared nav, footer, CSS design system
    ├── home.html                    ← Public landing page
    ├── about.html                   ← Mission & values
    ├── helplines.html               ← Emergency numbers (India, US, UK, Global)
    │
    ├── auth/
    │   ├── login.html               ← Staff login
    │   └── register.html            ← Therapist / Responder registration
    │
    ├── survivor/
    │   ├── home.html                ← Anonymous entry portal
    │   ├── analyse.html             ← Text + Voice emotion analysis form
    │   └── chat.html                ← Anonymous real-time therapy chat
    │
    ├── therapist/
    │   ├── dashboard.html           ← Session queues + live notifications
    │   └── session.html             ← Full chat + emotion profile + notes
    │
    ├── emergency/
    │   └── dashboard.html           ← Live high-risk case console
    │
    ├── admin/
    │   └── dashboard.html           ← User mgmt + audit log + stats
    │
    └── payment/
        ├── plans.html               ← Plan selection + therapist picker
        ├── success.html             ← Post-payment confirmation + confetti
        └── receipt.html             ← Printable anonymous receipt
```

---

## 🗄️ Database Schema (SQLite)

```
users               — therapists, admins, emergency responders
survivor_sessions   — anonymous sessions with emotion + risk data
chat_messages       — all chat history per session
payment_plans       — plan configs (price, sessions, validity)
payments            — every Razorpay transaction record
subscriptions       — active recurring plans
escalation_logs     — high-risk case escalation history
audit_logs          — admin/therapist action trail
```

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.10 or higher → [python.org](https://python.org)
- pip (comes with Python)
- Internet connection (downloads AI model ~500MB on first run)

---

### Step 1 — Extract the Project
After downloading, extract the zip file. Open your terminal inside the `safevoice` folder.

**Windows:** Click the address bar in the folder → type `cmd` → press Enter

**Mac/Linux:** Right-click inside the folder → "Open Terminal here"

---

### Step 2 — Create a Virtual Environment
```bash
python -m venv venv
```

Activate it:
```bash
# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```
You will see `(venv)` appear in your terminal — that means it is active.

---

### Step 3 — Install Dependencies
```bash
pip install -r requirements.txt
```

> First install takes 3–8 minutes (PyTorch + Transformers are large).
> For a faster install, use the CPU-only PyTorch version:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```

---

### Step 4 — Configure Environment Variables
```bash
# Mac / Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Open `.env` in any text editor and fill in your values:
```env
SECRET_KEY=any-long-random-string-change-this
RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXX
RAZORPAY_KEY_SECRET=your_razorpay_secret_here
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here
```

Get free Razorpay test keys at → **dashboard.razorpay.com → Settings → API Keys**

Then add these 2 lines at the very top of `app.py` (above all other imports):
```python
from dotenv import load_dotenv
load_dotenv()
```

And install python-dotenv:
```bash
pip install python-dotenv
```

---

### Step 5 — (Optional) Audio Support
For the voice recording / speech-to-text feature:

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
# Add ffmpeg to your system PATH
```

---

### Step 6 — Run the Application
```bash
python app.py
```

**You should see:**
```
[emotion_model] Loading HuggingFace model…
[emotion_model] Model ready.
[DB] Default admin created: admin@safevoice.org / Admin@123
* Running on http://0.0.0.0:5000
* Press CTRL+C to quit
```

> The first run downloads the AI model (~500MB). This only happens once.
> All future runs start in seconds.

---

### Step 7 — Open in Browser
```
http://localhost:5000
```

---

## 🔑 Default Login Credentials

| Role | Email | Password | Notes |
|------|-------|----------|-------|
| **Admin** | admin@safevoice.org | Admin@123 | Auto-created on first run |
| **Therapist** | Register at `/register` | Your choice | Needs admin approval |
| **Emergency** | Register at `/register` | Your choice | Auto-approved instantly |
| **Survivor** | *No login needed* | — | Go directly to `/survivor` |

---

## 💳 Payment Plans (Auto-Seeded on First Run)

| Plan | Type | Price | Sessions | Validity |
|------|------|-------|----------|----------|
| Single Session | One-time | ₹499 | 1 | 1 day |
| 3-Session Pack | One-time | ₹1,299 | 3 | 30 days |
| Weekly Care Plan | Subscription | ₹999/week | 3/week | 7 days |
| Monthly Healing Plan | Subscription | ₹2,999/month | 12/month | 30 days |

---

## 🧪 Testing Payments (No Real Money)

Use these Razorpay test card details in the checkout popup:

```
Card Number  :  4111 1111 1111 1111
Expiry       :  Any future date   (e.g. 12/26)
CVV          :  Any 3 digits      (e.g. 123)
OTP          :  1234
```

---

## 🔌 API Endpoints Reference

### Survivor (Public — No Login)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| GET | `/survivor` | Survivor portal |
| GET | `/survivor/analyse` | Analysis page (text + voice) |
| POST | `/api/analyse` | Submit text → emotion + risk result |
| POST | `/api/analyse-audio` | Submit audio file → transcribe → analyse |
| GET | `/survivor/chat/<uuid>` | Anonymous chat room |

### Payment
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/payment/plans/<uuid>` | Plan selection + therapist picker |
| POST | `/payment/create-order` | Create Razorpay one-time order |
| POST | `/payment/create-subscription` | Create Razorpay subscription |
| POST | `/payment/verify` | Verify payment signature server-side |
| POST | `/payment/webhook` | Razorpay webhook event listener |
| GET | `/payment/success/<uuid>` | Payment success + confetti |
| GET | `/payment/receipt/<ref>` | Printable anonymous receipt |

### Therapist (Login Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/therapist` | Dashboard with session queues |
| GET | `/therapist/session/<uuid>` | Session chat + emotion profile |
| POST | `/api/therapist/accept/<uuid>` | Accept a pending session |
| POST | `/api/therapist/resolve/<uuid>` | Resolve session + save notes |

### Emergency Responder (Login Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/emergency` | Live escalation dashboard |
| POST | `/api/emergency/respond/<uuid>` | Log emergency response action |

### Admin (Login Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin` | Full admin dashboard |
| POST | `/api/admin/approve/<id>` | Approve therapist account |
| POST | `/api/admin/disable/<id>` | Disable user account |

---

## ⚡ Real-Time SocketIO Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `send_message` | Client → Server | Send a chat message |
| `receive_message` | Server → Client | Receive a chat message |
| `new_session` | Server → Therapists | New Moderate/High session assigned |
| `new_high_risk` | Server → Emergency | High risk case detected |
| `session_accepted` | Server → Survivor | Therapist has joined |

---

## 🤖 How the AI Risk Engine Works

```
User Input (text or voice)
        │
        ▼
  HuggingFace distilroberta
  → 7 emotion scores
        │
        ▼
  Weighted severity formula:
  fear×0.5 + sadness×0.3 + anger×0.2
  = score between 0.0 and 1.0
        │
        ▼
  score < 0.40   →  LOW      → Self-help tips
  score 0.40–0.75 → MODERATE → Therapist chat
  score > 0.75   →  HIGH     → Emergency alert
```

---

## 🌐 Emergency Helplines in the Platform

| Country | Service | Number |
|---------|---------|--------|
| 🇮🇳 India | iCall Mental Health | 9152987821 |
| 🇮🇳 India | Vandrevala Foundation (24×7) | 1860-2662-345 |
| 🇮🇳 India | Women Helpline | 1091 |
| 🇮🇳 India | Emergency | 112 |
| 🇺🇸 USA | RAINN Sexual Assault Hotline | 1-800-656-4673 |
| 🇺🇸 USA | Crisis Text Line | Text HOME → 741741 |
| 🇺🇸 USA | Suicide & Crisis Lifeline | 988 |
| 🇬🇧 UK | Samaritans | 116 123 |
| 🇬🇧 UK | Emergency | 999 |

---

## ❗ Common Errors & Fixes

**`ModuleNotFoundError: No module named 'flask'`**
```bash
# Virtual environment is not active — run this first:
venv\Scripts\activate      # Windows
source venv/bin/activate   # Mac/Linux
```

**`ModuleNotFoundError: No module named 'razorpay'`**
```bash
pip install razorpay
```

**PyTorch download is very slow or fails**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

**Port 5000 already in use**
```python
# Change the last line in app.py:
socketio.run(app, host="0.0.0.0", port=5001, debug=True)
# Then open: http://localhost:5001
```

**`ffmpeg not found` (voice recording not working)**
```bash
sudo apt install ffmpeg    # Ubuntu
brew install ffmpeg        # macOS
# Windows: https://ffmpeg.org → download → add to PATH
```

**Razorpay payment verification fails**
Check that `RAZORPAY_KEY_SECRET` in your `.env` matches exactly what is shown in the Razorpay dashboard — no extra spaces or newlines.

**HuggingFace model download stuck**
This is normal on first run — the model is ~500MB. Wait for it to complete. If it fails, delete the `~/.cache/huggingface` folder and try again.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend Framework | Python 3.10+, Flask 3.0 |
| Database | SQLite + SQLAlchemy ORM |
| Authentication | Flask-Login + Werkzeug PBKDF2 hashing |
| Real-time Chat | Flask-SocketIO (WebSockets) |
| AI / NLP | HuggingFace Transformers (distilroberta) |
| Speech-to-Text | Google Speech Recognition API |
| Payments | Razorpay Python SDK |
| Frontend | Jinja2, Vanilla JS, CSS3 |
| Fonts | Google Fonts (Cormorant Garamond + DM Sans) |

---

## 🔒 Security & Privacy Summary

| Feature | Implementation |
|---------|---------------|
| Survivor anonymity | Random UUID per session, zero PII stored |
| Password security | PBKDF2-SHA256 via Werkzeug |
| Payment security | HMAC-SHA256 server-side Razorpay verification |
| Access control | Role-based decorators on all staff routes |
| Audit trail | Every staff action logged with timestamp + IP |
| Audio privacy | Files deleted immediately after transcription |
| Receipt privacy | No name or contact info on any receipt |

---

## 📄 License

Built for educational and hackathon purposes.
If deploying to production, conduct a full security audit and comply with applicable data protection laws.

---

*SafeVoice — Built with 💜 for women who deserve to be heard and protected.*