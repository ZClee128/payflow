import os
from sqlalchemy import text
from database import engine

def fix():
    columns_to_add = [
        ("orders", "order_no", "VARCHAR"),
        ("orders", "merchant_id", "INTEGER"),
        ("users", "is_superadmin", "BOOLEAN DEFAULT FALSE"),
        ("users", "alipay_uid", "VARCHAR"),
        ("users", "points_balance", "FLOAT DEFAULT 0.0")
    ]
    
    print("🚀 Starting Manual Database Fix (Transaction Safe)...")
    
    for table, col, col_type in columns_to_add:
        # Each column gets its own fresh connection/transaction
        with engine.connect() as conn:
            try:
                print(f"Adding {col} to {table}...", end=" ", flush=True)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
                conn.commit()
                print("✅")
            except Exception as e:
                # Cleanup transaction state
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("ℹ️ Exists")
                else:
                    print(f"❌ Error: {e}")
    
    print("\n✨ Database fix completed!")
        
    print("\n✨ Database fix completed!")

if __name__ == "__main__":
    fix()
