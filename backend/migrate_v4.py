from sqlalchemy import text
from database import engine

def migrate():
    with engine.connect() as conn:
        print("🚀 Adding payment_source column to orders table...")
        try:
            conn.execute(text("ALTER TABLE orders ADD COLUMN payment_source VARCHAR;"))
            conn.commit()
            print("✅ Migration successful!")
        except Exception as e:
            print(f"⚠️ Migration skipped or failed: {e}")

if __name__ == "__main__":
    migrate()
