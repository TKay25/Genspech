import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+pg8000://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+pg8000://" + url[len("postgresql://") :]
    return url


app = Flask(__name__)


def _normalize_site_url(url: str) -> str:
    """Make sure SITE_URL is an absolute URL with no trailing slash.

    Accepts 'www.genspech.co.zw' or 'genspech.co.zw' (scheme added) as well
    as fully-qualified 'https://www.genspech.co.zw'.
    """
    url = (url or "").strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


# Public site URL used for canonical tags, sitemap and structured data.
# Override with the SITE_URL env var if needed (e.g. staging).
SITE_URL = _normalize_site_url(os.getenv("SITE_URL", "https://www.genspech.co.zw"))

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
    "boom-pump": 700.0,
    "static-pump": 500.0,
    "power-float": 120.0,
    "poker": 30.0,
    "3.5-cubic": 500.0,
    "1-cubic-manual": 200.0,
    "mixer-truck": 450.0,
    "lowbed": 3.0,
    "side-curtain": 3.0,
}

URGENCY_MULTIPLIER = {
    "standard": 1.0,
    "priority": 1.15,
    "urgent": 1.3,
}

MACHINE_NAMES = {
    "generator": "Generator Hire",
    "boom-pump": "Concrete Boom Pump",
    "static-pump": "Concrete Static Pump",
    "power-float": "Power Float",
    "poker": "Poker Vibrator",
    "3.5-cubic": "Self Loading Concrete Mixer (3.5 Cubic)",
    "mixer-truck": "Concrete Mixer Truck (Transit Mixer)",
    "1-cubic-manual": "1 Cubic Manual Loading Mixer",
    "lowbed": "Lowbed Transport (per km)",
    "side-curtain": "Side Curtain Truck",
}

MACHINE_ALIASES = {
    "generator": "generator",
    "genset": "generator",
    "self loader": "3.5-cubic",
    "self-loading": "3.5-cubic",
    "self loading": "3.5-cubic",
    "mixer truck": "mixer-truck",
    "transit mixer": "mixer-truck",
    "ready mix": "mixer-truck",
    "ready-mix": "mixer-truck",
    "mixer": "3.5-cubic",
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
    "lowbed": "lowbed",
    "low bed": "lowbed",
    "low-bed": "lowbed",
    "side curtain": "side-curtain",
    "curtain side": "side-curtain",
    "curtainsider": "side-curtain",
    "sidecurtain": "side-curtain",
    "superlink": "side-curtain",
    "transport": "lowbed",
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


class SiteContent(db.Model):
    """Simple key/value store for site-wide settings (hero images, etc.)."""

    __tablename__ = "genspech_site_content"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="{}")


class HireCard(db.Model):
    """Content-managed hire cards shown in the Machines / Vehicles sections."""

    __tablename__ = "genspech_hire_cards"

    id = db.Column(db.Integer, primary_key=True)
    machine_key = db.Column(db.String(60), nullable=False, default="")
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.String(400), nullable=False, default="")
    price = db.Column(db.String(60), nullable=False, default="")
    image = db.Column(db.String(200), nullable=False, default="")
    section = db.Column(db.String(20), nullable=False, default="machines")  # machines | vehicles
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)


class GalleryItem(db.Model):
    """Content-managed entries for the Recent Projects gallery."""

    __tablename__ = "genspech_gallery_items"

    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=False, default="")
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.String(400), nullable=False, default="")
    featured = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)


class Section(db.Model):
    """Content-managed hire sections (Machines, Vehicles, custom sections...)."""

    __tablename__ = "genspech_sections"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(60), unique=True, nullable=False)
    title = db.Column(db.String(140), nullable=False)
    kicker = db.Column(db.String(140), nullable=False, default="")
    nav_label = db.Column(db.String(60), nullable=False, default="")
    description = db.Column(db.String(300), nullable=False, default="")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)


def get_content(key: str, default: str = "") -> str:
    row = db.session.get(SiteContent, key)
    return row.value if row else default


DEFAULT_SECTIONS = [
    # (key, title, kicker, nav_label, description)
    ("machines", "Machines We Hire", "Machines Available For Hire", "Concrete Mixers", "Machines, pumps and finishing equipment available for hire across Zimbabwe."),
    ("vehicles", "Vehicles We Hire", "Vehicles Available For Hire", "Vehicles", "Heavy transport to move your construction & mining equipment safely across Zimbabwe."),
]


DEFAULT_HIRE_CARDS = [
    # (machine_key, title, description, price, image, section)
    ("3.5-cubic", "Self-Loading Concrete Mixer (3.5 Cubic)", "Combines cement, water & aggregates for reliable site mixing.", "From $500/day", "selfloadingmixer.jpeg", "machines"),
    ("static-pump", "Concrete Static Pump", "Essential for efficient concrete pumping on any site.", "From $500/day", "static pump.jpeg", "machines"),
    ("boom-pump", "Concrete Boom Pump", "Precision & reliability in concrete placement.", "From $700/day", "boom pump.jpeg", "machines"),
    ("power-float", "Power Float", "Smooth & finish concrete surfaces to a high standard.", "From $120/day", "powerfloat.jpeg", "machines"),
    ("poker", "Poker Vibrator", "Eliminate air pockets in fresh concrete.", "From $30/day", "concrete vibrator or poker.jpeg", "machines"),
    ("1-cubic-manual", "1 Cubic Manual Mixer", "Compact manual-loading blue unit — $200/day.", "From $200/day", "mixer 2.jpeg", "machines"),
    ("mixer-truck", "Concrete Mixer Truck (Transit Mixer)", "Loads concrete from the batch plant to the customer.", "From $450/day", "mixer truck.jpeg", "machines"),
    ("lowbed", "Lowbed Transport", "Heavy-duty lowbed to ferry construction & mining machines — excavators, loaders, rollers, backhoes, generators and more — $3/km across Zimbabwe.", "From $3/km", "lowbed.jpeg", "vehicles"),
    ("side-curtain", "Side Curtain Truck", "Used for carrying pallets, building materials, machinery, general freight and agricultural products — crossborder transport available.", "From $3/km", "sidecurtaintruck30tonnesuperlink.jpeg", "vehicles"),
]

DEFAULT_GALLERY = [
    # (image, category, title, description, featured)
    ("concrete4.jpeg", "Concrete Placement", "Boom Pump Placement", "High-reach concrete placement for multi-storey structures — precision and reliability on every pour.", True),
    ("concrete5.jpeg", "Concrete Pumping", "Concrete Pumping", "Reliable line pumping for slabs, footings and foundations.", False),
    ("concrete-mixer.jpg", "Site Concreting", "Site Concreting", "Mixer-supported pours keeping sites moving on schedule.", False),
    ("concrete6.jpeg", "Finishing", "Surface Finishing", "Power-float finishing for smooth, level concrete floors.", False),
    ("concrete3.jpeg", "Concrete Works", "Concrete Works", "Complete pours with vibration and curing for lasting strength.", False),
    ("generator.jpg", "Power", "Power Solutions", "Generator backup keeping sites powered around the clock.", False),
]

DEFAULT_HERO_IMAGES = [
    "mixer truck.jpeg",
    "generator.jpg",
    "boom pump.jpeg",
    "static pump.jpeg",
    "mobile concrete mixer.jpeg",
    "concrete vibrator or poker.jpeg",
]


def seed_default_content() -> None:
    """Populate content tables + site settings on first run."""
    if Section.query.count() == 0:
        for i, (key, title, kicker, nav, desc) in enumerate(DEFAULT_SECTIONS):
            db.session.add(
                Section(
                    key=key, title=title, kicker=kicker,
                    nav_label=nav, description=desc, sort_order=i + 1,
                )
            )
    if HireCard.query.count() == 0:
        for i, (mk, title, desc, price, image, section) in enumerate(DEFAULT_HIRE_CARDS):
            db.session.add(
                HireCard(
                    machine_key=mk, title=title, description=desc,
                    price=price, image=image, section=section, sort_order=i + 1,
                )
            )
    if GalleryItem.query.count() == 0:
        for i, (image, cat, title, desc, featured) in enumerate(DEFAULT_GALLERY):
            db.session.add(
                GalleryItem(
                    image=image, category=cat, title=title,
                    description=desc, featured=featured, sort_order=i + 1,
                )
            )
    if db.session.get(SiteContent, "hero_images") is None:
        db.session.add(SiteContent(key="hero_images", value=json.dumps(DEFAULT_HERO_IMAGES)))
    db.session.commit()


@dataclass
class QuoteResult:
    machine: str
    machine_name: str
    days: int
    urgency: str
    daily_rate: float
    subtotal: float
    total: float
    unit: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "machine": self.machine,
            "machineName": self.machine_name,
            "days": self.days,
            "urgency": self.urgency,
            "dailyRate": round(self.daily_rate, 2),
            "subtotal": round(self.subtotal, 2),
            "total": round(self.total, 2),
            "unit": self.unit,
        }


PER_KM_MACHINES = {"lowbed", "side-curtain"}


def build_quote(machine: str, days: int, urgency: str) -> QuoteResult:
    if machine not in RATES:
        raise ValueError("Unsupported machine type")
    if urgency not in URGENCY_MULTIPLIER:
        raise ValueError("Unsupported urgency level")
    if machine in PER_KM_MACHINES:
        if days < 1 or days > 20000:
            raise ValueError("Distance must be between 1 and 20000 km")
        unit = "km"
    else:
        if days < 1 or days > 365:
            raise ValueError("Days must be between 1 and 365")
        unit = "days"

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
        unit=unit,
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

    standalone = re.search(r"\b(\d{1,5})\b", message)
    if standalone:
        return int(standalone.group(1))
    return None


def extract_km(message: str) -> int | None:
    match = re.search(r"\b(\d{1,5})\s*(?:km|kms|kilometre|kilometer|kilometres|kilometers|k)\b", message.lower())
    if match:
        return int(match.group(1))
    standalone = re.search(r"\b(\d{1,5})\b", message)
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
    detected_urgency = extract_urgency(cleaned)

    if detected_machine:
        new_context["machine"] = detected_machine
    if detected_urgency:
        new_context["urgency"] = detected_urgency

    # Lowbed is billed per km; other machines per day.
    is_km = new_context.get("machine") in PER_KM_MACHINES
    detected_qty = extract_km(cleaned) if is_km else extract_days(cleaned)
    if detected_qty is not None:
        new_context["days"] = detected_qty

    if any(word in lowered for word in ["hello", "hi", "hey"]):
        return (
            "Hi, I can prepare a hire estimate. Example: 'generator for 3 days urgent' or 'lowbed 150 km'.",
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
            prompt = "Tell me the machine and " + ("distance in km" if is_km else "number of days") + ". Example: " + ("lowbed 150 km" if is_km else "boom pump for 2 days") + "."
        elif "machine" in missing:
            prompt = "Which machine do you need? Generator, self loader, concrete boom pump, concrete static pump, power float, poker vibrator, or lowbed transport?"
        else:
            prompt = "How many " + ("kilometres of transport distance" if is_km else "days do you want to hire for") + "?"
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
        f"Estimated total for {quote.machine_name} ({quote.days} {quote.unit}, {quote.urgency}) is "
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
    seed_default_content()


@app.get("/")
def home() -> str:
    sections = (
        Section.query.filter_by(active=True)
        .order_by(Section.sort_order)
        .all()
    )
    sections_data = []
    for s in sections:
        cards = (
            HireCard.query.filter_by(active=True, section=s.key)
            .order_by(HireCard.sort_order)
            .all()
        )
        if cards:
            sections_data.append({"section": s, "cards": cards})
    gallery = (
        GalleryItem.query.filter_by(active=True)
        .order_by(GalleryItem.sort_order)
        .all()
    )
    try:
        hero_images = json.loads(get_content("hero_images", "[]"))
    except Exception:
        hero_images = []
    if not isinstance(hero_images, list):
        hero_images = []
    return render_template(
        "index.html",
        site_url=SITE_URL,
        sections_data=sections_data,
        gallery=gallery,
        hero_images=hero_images,
    )


@app.get("/robots.txt")
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        "\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{SITE_URL}/</loc><lastmod>2026-08-16</lastmod>'
        "<changefreq>weekly</changefreq><priority>1.0</priority></url>\n"
        "</urlset>\n"
    )
    return Response(xml, mimetype="application/xml")


@app.get("/<path:filename>")
def google_verification(filename: str):
    """Serve Google Search Console HTML verification files (e.g. google1234....html).

    Google's HTML-file method only checks that the file exists at the site root and
    contains a single line: 'google-site-verification: <filename>'. The token is
    embedded in the filename Google generates, so we can serve it directly. If you'd
    rather use the actual downloaded file, drop it into the /verification folder and
    it will be served byte-for-byte instead.
    """
    if re.fullmatch(r"google[a-zA-Z0-9_-]+\.html", filename):
        local = os.path.join("verification", filename)
        if os.path.isfile(local):
            return send_from_directory("verification", filename)
        return Response(f"google-site-verification: {filename}\n", mimetype="text/html")
    abort(404)


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
    cards = HireCard.query.order_by(HireCard.section, HireCard.sort_order).all()
    gallery_items = GalleryItem.query.order_by(GalleryItem.sort_order).all()
    sections = Section.query.order_by(Section.sort_order).all()
    try:
        image_library = sorted(
            f
            for f in os.listdir(os.path.join("static", "images"))
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
        )
    except Exception:
        image_library = []
    try:
        hero_list = json.loads(get_content("hero_images", "[]"))
        hero_csv = ", ".join(hero_list) if isinstance(hero_list, list) else ""
    except Exception:
        hero_csv = ""
    return render_template(
        "admin.html",
        key=key,
        quotes=quotes,
        total_quotes=total_quotes,
        total_value=round(float(total_value), 2),
        total_downloads=total_downloads,
        cards=cards,
        gallery=gallery_items,
        sections=sections,
        image_library=image_library,
        hero_images=hero_csv,
    )


def _admin_ok() -> bool:
    expected = os.getenv("ADMIN_DASHBOARD_KEY", "genspech-admin")
    return request.args.get("key", request.form.get("key", "")) == expected


def _admin_redirect(tab: str = "overview") -> str:
    key = request.args.get("key", request.form.get("key", ""))
    return redirect(f"/admin?key={key}&tab={tab}")


ALLOWED_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def _uploaded_image(file) -> str | None:
    """Save an uploaded image into static/images and return its filename."""
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    if not filename.lower().endswith(ALLOWED_IMAGE_EXT):
        return None
    dest = os.path.join("static", "images", filename)
    try:
        file.save(dest)
        return filename
    except Exception:
        return None


@app.post("/admin/card/add")
def admin_card_add():
    if not _admin_ok():
        abort(403)
    title = request.form.get("title", "").strip()
    if title:
        image = (request.form.get("image", "") or "").strip()
        up = _uploaded_image(request.files.get("image_file"))
        if up:
            image = up
        section = request.form.get("section", "machines")
        max_order = db.session.query(
            db.func.coalesce(db.func.max(HireCard.sort_order), 0)
        ).scalar() or 0
        db.session.add(
            HireCard(
                machine_key=request.form.get("machine_key", "").strip(),
                title=title,
                description=request.form.get("description", "").strip(),
                price=request.form.get("price", "").strip(),
                image=image,
                section=section,
                sort_order=max_order + 1,
            )
        )
        db.session.commit()
    return _admin_redirect("cards")


@app.post("/admin/card/edit")
def admin_card_edit():
    if not _admin_ok():
        abort(403)
    card = db.session.get(HireCard, int(request.form.get("id", 0) or 0))
    if card:
        card.machine_key = request.form.get("machine_key", card.machine_key).strip()
        card.title = request.form.get("title", card.title).strip()
        card.description = request.form.get("description", card.description).strip()
        card.price = request.form.get("price", card.price).strip()
        typed_image = (request.form.get("image", "") or "").strip()
        up = _uploaded_image(request.files.get("image_file"))
        if up:
            card.image = up
        elif typed_image:
            card.image = typed_image
        card.section = request.form.get("section", card.section)
        card.active = request.form.get("active", "1") == "1"
        db.session.commit()
    return _admin_redirect("cards")


@app.post("/admin/card/move")
def admin_card_move():
    if not _admin_ok():
        abort(403)
    card = db.session.get(HireCard, int(request.form.get("id", 0) or 0))
    if card:
        direction = request.form.get("dir", "up")
        q = HireCard.query.filter(
            HireCard.section == card.section, HireCard.id != card.id
        )
        if direction == "up":
            neighbor = (
                q.filter(HireCard.sort_order < card.sort_order)
                .order_by(HireCard.sort_order.desc())
                .first()
            )
        else:
            neighbor = (
                q.filter(HireCard.sort_order > card.sort_order)
                .order_by(HireCard.sort_order.asc())
                .first()
            )
        if neighbor:
            card.sort_order, neighbor.sort_order = neighbor.sort_order, card.sort_order
            db.session.commit()
    return _admin_redirect("cards")


@app.post("/admin/card/reorder")
def admin_card_reorder():
    """Update card ordering after drag & drop within a section."""
    if not _admin_ok():
        abort(403)
    section = request.form.get("section", "")
    ids = [
        int(x) for x in request.form.get("ids", "").split(",")
        if x.strip().isdigit()
    ]
    for i, cid in enumerate(ids):
        card = db.session.get(HireCard, cid)
        if card and card.section == section:
            card.sort_order = i + 1
    db.session.commit()
    return _admin_redirect("sections")


@app.post("/admin/card/delete")
def admin_card_delete():
    if not _admin_ok():
        abort(403)
    card = db.session.get(HireCard, int(request.form.get("id", 0) or 0))
    if card:
        db.session.delete(card)
        db.session.commit()
    return _admin_redirect("cards")


@app.post("/admin/gallery/add")
def admin_gallery_add():
    if not _admin_ok():
        abort(403)
    title = request.form.get("title", "").strip()
    if title:
        image = (request.form.get("image", "") or "").strip()
        up = _uploaded_image(request.files.get("image_file"))
        if up:
            image = up
        max_order = db.session.query(
            db.func.coalesce(db.func.max(GalleryItem.sort_order), 0)
        ).scalar() or 0
        db.session.add(
            GalleryItem(
                image=image,
                category=request.form.get("category", "").strip(),
                title=title,
                description=request.form.get("description", "").strip(),
                featured=request.form.get("featured", "0") == "1",
                sort_order=max_order + 1,
            )
        )
        db.session.commit()
    return _admin_redirect("gallery")


@app.post("/admin/gallery/edit")
def admin_gallery_edit():
    if not _admin_ok():
        abort(403)
    item = db.session.get(GalleryItem, int(request.form.get("id", 0) or 0))
    if item:
        typed_image = (request.form.get("image", "") or "").strip()
        up = _uploaded_image(request.files.get("image_file"))
        if up:
            item.image = up
        elif typed_image:
            item.image = typed_image
        item.category = request.form.get("category", item.category).strip()
        item.title = request.form.get("title", item.title).strip()
        item.description = request.form.get("description", item.description).strip()
        item.featured = request.form.get("featured", "0") == "1"
        item.active = request.form.get("active", "1") == "1"
        db.session.commit()
    return _admin_redirect("gallery")


@app.post("/admin/gallery/move")
def admin_gallery_move():
    if not _admin_ok():
        abort(403)
    item = db.session.get(GalleryItem, int(request.form.get("id", 0) or 0))
    if item:
        direction = request.form.get("dir", "up")
        q = GalleryItem.query.filter(GalleryItem.id != item.id)
        if direction == "up":
            neighbor = (
                q.filter(GalleryItem.sort_order < item.sort_order)
                .order_by(GalleryItem.sort_order.desc())
                .first()
            )
        else:
            neighbor = (
                q.filter(GalleryItem.sort_order > item.sort_order)
                .order_by(GalleryItem.sort_order.asc())
                .first()
            )
        if neighbor:
            item.sort_order, neighbor.sort_order = neighbor.sort_order, item.sort_order
            db.session.commit()
    return _admin_redirect("gallery")


@app.post("/admin/gallery/delete")
def admin_gallery_delete():
    if not _admin_ok():
        abort(403)
    item = db.session.get(GalleryItem, int(request.form.get("id", 0) or 0))
    if item:
        db.session.delete(item)
        db.session.commit()
    return _admin_redirect("gallery")


@app.post("/admin/section/add")
def admin_section_add():
    if not _admin_ok():
        abort(403)
    title = request.form.get("title", "").strip()
    slug = (request.form.get("slug", "") or "").strip().lower().replace(" ", "-")
    if title and slug and db.session.get(Section, slug) is None:
        max_order = db.session.query(
            db.func.coalesce(db.func.max(Section.sort_order), 0)
        ).scalar() or 0
        db.session.add(
            Section(
                key=slug,
                title=title,
                kicker=request.form.get("kicker", "").strip(),
                nav_label=(request.form.get("nav_label", "").strip() or title),
                description=request.form.get("description", "").strip(),
                sort_order=max_order + 1,
            )
        )
        db.session.flush()
        # Cards added together with the section (from the modal repeater)
        card_titles = request.form.getlist("card_title")
        card_descs = request.form.getlist("card_desc")
        card_prices = request.form.getlist("card_price")
        card_images = request.form.getlist("card_image")
        card_mks = request.form.getlist("card_machine_key")
        card_files = request.files.getlist("card_image_file")
        n = max(len(card_titles), len(card_descs), len(card_prices), len(card_images), len(card_mks), len(card_files))
        for i in range(n):
            ct = card_titles[i].strip() if i < len(card_titles) else ""
            if not ct:
                continue
            image = card_images[i].strip() if i < len(card_images) else ""
            up = _uploaded_image(card_files[i]) if i < len(card_files) else None
            if up:
                image = up
            db.session.add(
                HireCard(
                    machine_key=card_mks[i].strip() if i < len(card_mks) else "",
                    title=ct,
                    description=card_descs[i].strip() if i < len(card_descs) else "",
                    price=card_prices[i].strip() if i < len(card_prices) else "",
                    image=image,
                    section=slug,
                    sort_order=i + 1,
                )
            )
        db.session.commit()
    return _admin_redirect("sections")


@app.post("/admin/section/edit")
def admin_section_edit():
    if not _admin_ok():
        abort(403)
    s = db.session.get(Section, int(request.form.get("id", 0) or 0))
    if s:
        s.title = request.form.get("title", s.title).strip()
        s.kicker = request.form.get("kicker", s.kicker).strip()
        s.nav_label = request.form.get("nav_label", s.nav_label).strip()
        s.description = request.form.get("description", s.description).strip()
        s.active = request.form.get("active", "1") == "1"
        db.session.commit()
    return _admin_redirect("sections")


@app.post("/admin/section/move")
def admin_section_move():
    if not _admin_ok():
        abort(403)
    s = db.session.get(Section, int(request.form.get("id", 0) or 0))
    if s:
        direction = request.form.get("dir", "up")
        q = Section.query.filter(Section.id != s.id)
        if direction == "up":
            neighbor = (
                q.filter(Section.sort_order < s.sort_order)
                .order_by(Section.sort_order.desc())
                .first()
            )
        else:
            neighbor = (
                q.filter(Section.sort_order > s.sort_order)
                .order_by(Section.sort_order.asc())
                .first()
            )
        if neighbor:
            s.sort_order, neighbor.sort_order = neighbor.sort_order, s.sort_order
            db.session.commit()
    return _admin_redirect("sections")


@app.post("/admin/section/delete")
def admin_section_delete():
    if not _admin_ok():
        abort(403)
    s = db.session.get(Section, int(request.form.get("id", 0) or 0))
    if s:
        HireCard.query.filter_by(section=s.key).delete()
        db.session.delete(s)
        db.session.commit()
    return _admin_redirect("sections")


@app.post("/admin/images/upload")
def admin_images_upload():
    if not _admin_ok():
        abort(403)
    for f in request.files.getlist("files"):
        _uploaded_image(f)
    return _admin_redirect("images")


@app.post("/admin/settings")
def admin_settings():
    if not _admin_ok():
        abort(403)
    hero = request.form.get("hero_images", "")
    items = [x.strip() for x in hero.split(",") if x.strip()]
    row = db.session.get(SiteContent, "hero_images")
    if row:
        row.value = json.dumps(items)
    else:
        db.session.add(SiteContent(key="hero_images", value=json.dumps(items)))
    db.session.commit()
    return _admin_redirect("settings")


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