"""One-time script: replace all hire cards in the database with the current
DEFAULT_HIRE_CARDS list from app.py.

Run from the repo root with the app's Python environment:
    python sync_cards.py

This deletes every row in the genspech_hire_cards table and re-seeds it from
DEFAULT_HIRE_CARDS, so the homepage matches the code exactly.
"""
from app import DEFAULT_HIRE_CARDS, HireCard, app, db

with app.app_context():
    n = HireCard.query.count()
    HireCard.query.delete()
    for i, (mk, title, desc, price, image, section) in enumerate(DEFAULT_HIRE_CARDS):
        db.session.add(
            HireCard(
                machine_key=mk, title=title, description=desc,
                price=price, image=image, section=section, sort_order=i + 1,
            )
        )
    db.session.commit()
    print(f"Replaced {n} hire card(s) with {len(DEFAULT_HIRE_CARDS)} from DEFAULT_HIRE_CARDS.")
