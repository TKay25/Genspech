import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import Flask, abort, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+pg8000://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+pg8000://" + url[len("postgresql://") :]
    return url


app = Flask(__name__)
raw_database_url = os.getenv(
    "DATABASE_URL",
    "postgresql://lmsdatabase_8ag3_user:6WD9lOnHkiU7utlUUjT88m4XgEYQMTLb@dpg-ctp9h0aj1k6c739h9di0-a.oregon-postgres.render.com/lmsdatabase_8ag3",
)
app.config["SQLALCHEMY_DATABASE_URI"] = normalize_database_url(raw_database_url)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)

RATES = {
    "generator": 180.0,
    "self-loader": 420.0,
    "boom-pump": 650.0,
    "static-pump": 480.0,
    "power-float": 120.0,
    "poker": 90.0,
    "3.5-cubic": 550.0,
    "1-cubic-manual": 200.0,
}

URGENCY_MULTIPLIER = {
    "standard": 1.0,
    "priority": 1.15,
    "urgent": 1.3,
}

MACHINE_NAMES = {
    "generator": "Generator Hire",
    "self-loader": "Self Loading Concrete Mixer",
    "boom-pump": "Boom Pump",
    "static-pump": "Static Pump",
    "power-float": "Power Float",
    "poker": "Poker Vibrator",
    "3.5-cubic": "3.5 Cubic Concrete Mixer (Dry Rate)",
    "1-cubic-manual": "1 Cubic Manual Loading Mixer",
}

MACHINE_ALIASES = {
    "generator": "generator",
    "genset": "generator",
    "self loader": "self-loader",
    "self-loading": "self-loader",
    "self loading": "self-loader",
    "mixer": "self-loader",
    "boom": "boom-pump",
    "boom pump": "boom-pump",
    "static": "static-pump",
    "static pump": "static-pump",
    "power float": "power-float",
    "float": "power-float",
    "poker": "poker",
    "vibrator": "poker",
    "3.5 cubic": "3.5-cubic",
    "3.5cu": "3.5-cubic",
    "dry rate": "3.5-cubic",
    "1 cubic": "1-cubic-manual",
    "manual loading": "1-cubic-manual",
    "blue": "1-cubic-manual",
}


class QuoteRequest(db.Model):
    __tablename__ = "quote_requests"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    machine = db.Column(db.String(60), nullable=False)
    urgency = db.Column(db.String(30), nullable=False)
    days = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(30), nullable=False, default="form")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class LeadLog(db.Model):
    """Lightweight log of every name/phone captured when a visitor generates a
    quote or downloads a quote PDF. action is either "quote" or "download"."""

    __tablename__ = "lead_logs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    machine = db.Column(db.String(60), nullable=True)
    action = db.Column(db.String(20), nullable=False, default="quote")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


@dataclass
class QuoteResult:
    machine: str
    machine_name: str
    days: int
    urgency: str
    daily_rate: float
    subtotal: float
    total: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "machine": self.machine,
            "machineName": self.machine_name,
            "days": self.days,
            "urgency": self.urgency,
            "dailyRate": round(self.daily_rate, 2),
            "subtotal": round(self.subtotal, 2),
            "total": round(self.total, 2),
        }


def build_quote(machine: str, days: int, urgency: str) -> QuoteResult:
    if machine not in RATES:
        raise ValueError("Unsupported machine type")
    if urgency not in URGENCY_MULTIPLIER:
        raise ValueError("Unsupported urgency level")
    if days < 1 or days > 365:
        raise ValueError("Days must be between 1 and 365")

    daily_rate = RATES[machine]
    subtotal = daily_rate * days
    total = subtotal * URGENCY_MULTIPLIER[urgency]

    return QuoteResult(
        machine=machine,
        machine_name=MACHINE_NAMES[machine],
        days=days,
        urgency=urgency,
        daily_rate=daily_rate,
        subtotal=subtotal,
        total=total,
    )


def extract_machine(message: str) -> str | None:
    lowered = message.lower()
    for alias, key in MACHINE_ALIASES.items():
        if alias in lowered:
            return key
    return None


def extract_days(message: str) -> int | None:
    match = re.search(r"\b(\d{1,3})\s*(?:day|days|d)\b", message.lower())
    if match:
        return int(match.group(1))

    standalone = re.search(r"\b(\d{1,3})\b", message)
    if standalone:
        return int(standalone.group(1))
    return None


def extract_urgency(message: str) -> str | None:
    lowered = message.lower()
    if "urgent" in lowered or "same day" in lowered:
        return "urgent"
    if "priority" in lowered or "24h" in lowered:
        return "priority"
    if "standard" in lowered or "48h" in lowered:
        return "standard"
    return None


def chatbot_reply(message: str, context: dict[str, Any]) -> tuple[str, dict[str, Any], QuoteResult | None]:
    cleaned = message.strip()
    lowered = cleaned.lower()
    new_context: dict[str, Any] = {
        "machine": context.get("machine"),
        "days": context.get("days"),
        "urgency": context.get("urgency", "standard"),
    }

    if lowered in {"reset", "start over", "clear"}:
        return (
            "Chat reset. Tell me machine type, number of days, and urgency (standard, priority, urgent).",
            {"machine": None, "days": None, "urgency": "standard"},
            None,
        )

    detected_machine = extract_machine(cleaned)
    detected_days = extract_days(cleaned)
    detected_urgency = extract_urgency(cleaned)

    if detected_machine:
        new_context["machine"] = detected_machine
    if detected_days is not None:
        new_context["days"] = detected_days
    if detected_urgency:
        new_context["urgency"] = detected_urgency

    if any(word in lowered for word in ["hello", "hi", "hey"]):
        return (
            "Hi, I can prepare a hire estimate. Example: 'generator for 3 days urgent'.",
            new_context,
            None,
        )

    missing = []
    if not new_context.get("machine"):
        missing.append("machine")
    if not new_context.get("days"):
        missing.append("days")

    if missing:
        if missing == ["machine", "days"]:
            prompt = "Tell me the machine and number of days. Example: boom pump for 2 days."
        elif "machine" in missing:
            prompt = "Which machine do you need? Generator, self loader, boom pump, static pump, power float, or poker vibrator?"
        else:
            prompt = "How many days do you want to hire for?"
        return (prompt, new_context, None)

    try:
        quote = build_quote(
            machine=str(new_context["machine"]),
            days=int(new_context["days"]),
            urgency=str(new_context.get("urgency", "standard")),
        )
    except ValueError as exc:
        return (f"I could not calculate that quote: {exc}.", new_context, None)

    reply = (
        f"Estimated total for {quote.machine_name} ({quote.days} day(s), {quote.urgency}) is "
        f"${quote.total:.2f}. Reply with 'reset' to start another quote."
    )
    return (reply, new_context, quote)


def save_quote_request(
    *,
    machine: str,
    urgency: str,
    days: int,
    total: float,
    source: str,
    name: str | None = None,
    phone: str | None = None,
) -> int:
    record = QuoteRequest(
        name=name,
        phone=phone,
        machine=machine,
        urgency=urgency,
        days=days,
        total=total,
        source=source,
    )
    db.session.add(record)
    db.session.commit()
    return int(record.id)


def log_lead(*, action: str, name: str | None, phone: str | None, machine: str | None) -> None:
    """Record a lead event (quote generated or PDF downloaded). Never raises,
    so logging can't break the request that triggered it."""
    if not name and not phone:
        return
    try:
        db.session.add(LeadLog(name=name, phone=phone, machine=machine, action=action))
        db.session.commit()
    except Exception:
        db.session.rollback()


@app.before_request
def init_db() -> None:
    db.create_all()


@app.get("/")
def home() -> str:
    return render_template("index.html")


@app.get("/admin")
def admin() -> str:
    key = request.args.get("key", "")
    expected_key = os.getenv("ADMIN_DASHBOARD_KEY", "genspech-admin")
    if key != expected_key:
        abort(403)

    quotes = QuoteRequest.query.order_by(QuoteRequest.created_at.desc()).limit(200).all()
    total_quotes = QuoteRequest.query.count()
    total_value = db.session.query(db.func.coalesce(db.func.sum(QuoteRequest.total), 0.0)).scalar() or 0.0
    total_downloads = LeadLog.query.filter_by(action="download").count()
    return render_template(
        "admin.html",
        quotes=quotes,
        total_quotes=total_quotes,
        total_value=round(float(total_value), 2),
        total_downloads=total_downloads,
    )


@app.post("/api/quote")
def api_quote():
    payload = request.get_json(silent=True) or {}

    machine = str(payload.get("machine", "")).strip()
    urgency = str(payload.get("urgency", "standard")).strip().lower()
    name = str(payload.get("name", "")).strip() or None
    phone = str(payload.get("phone", "")).strip() or None

    try:
        days = int(payload.get("days", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Days must be a valid number"}), 400

    try:
        quote = build_quote(machine=machine, days=days, urgency=urgency)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    quote_id = save_quote_request(
        machine=quote.machine,
        urgency=quote.urgency,
        days=quote.days,
        total=quote.total,
        source="form",
        name=name,
        phone=phone,
    )
    log_lead(action="quote", name=name, phone=phone, machine=quote.machine)

    return jsonify({"ok": True, "quote": quote.as_dict(), "quoteId": quote_id})


@app.post("/api/log-download")
def api_log_download():
    """Client calls this when a visitor clicks Download Quote."""
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip() or None
    phone = str(payload.get("phone", "")).strip() or None
    machine = str(payload.get("machine", "")).strip() or None
    log_lead(action="download", name=name, phone=phone, machine=machine)
    return jsonify({"ok": True})


@app.get("/api/export-log")
def api_export_log():
    """Password-protected export of the captured contact log (JSON)."""
    key = request.args.get("key", "")
    expected_key = os.getenv("ADMIN_DASHBOARD_KEY", "genspech-admin")
    if key != expected_key:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    logs = LeadLog.query.order_by(LeadLog.created_at.desc()).limit(1000).all()
    data = [
        {
            "id": r.id,
            "name": r.name or "",
            "phone": r.phone or "",
            "machine": r.machine or "",
            "action": r.action,
            "created": r.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for r in logs
    ]
    return jsonify({"ok": True, "count": len(data), "logs": data})


@app.post("/api/chatbot")
def api_chatbot():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    context = payload.get("context") or {}
    name = str(payload.get("name", "")).strip() or None
    phone = str(payload.get("phone", "")).strip() or None

    if not message:
        return jsonify({"ok": False, "error": "Message is required"}), 400

    response_text, updated_context, quote = chatbot_reply(message, context)

    response_payload: dict[str, Any] = {
        "ok": True,
        "response": response_text,
        "context": updated_context,
    }
    if quote:
        quote_id = save_quote_request(
            machine=quote.machine,
            urgency=quote.urgency,
            days=quote.days,
            total=quote.total,
            source="chatbot",
            name=name,
            phone=phone,
        )
        log_lead(action="quote", name=name, phone=phone, machine=quote.machine)
        response_payload["quote"] = quote.as_dict()
        response_payload["quoteId"] = quote_id

    return jsonify(response_payload)


@app.get("/health")
def health():
    return jsonify({"ok": True, "status": "healthy"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)