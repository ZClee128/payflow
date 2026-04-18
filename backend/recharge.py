from sqlalchemy import text
from database import engine

with engine.connect() as conn:
    conn.execute(text("UPDATE users SET points_balance = 100.0 WHERE id = 1;"))
    conn.commit()
    print("✅ Successfully recharged 100.0 points to merchant ID 1.")
