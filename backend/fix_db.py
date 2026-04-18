import os
from sqlalchemy import text
from database import engine

def fix():
    # Phase 1: Add Missing Columns
    columns_to_add = [
        ("orders", "order_no", "VARCHAR"),
        ("orders", "merchant_id", "INTEGER"),
        ("users", "is_superadmin", "BOOLEAN DEFAULT FALSE"),
        ("users", "alipay_uid", "VARCHAR"),
        ("users", "points_balance", "FLOAT DEFAULT 0.0")
    ]
    
    print("🚀 Phase 1: Adding Missing Columns...")
    for table, col, col_type in columns_to_add:
        with engine.connect() as conn:
            try:
                print(f"Checking {col} in {table}...", end=" ", flush=True)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
                conn.commit()
                print("✅ Added")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("ℹ️ Exists")
                else:
                    print(f"❌ Error: {e}")

    # Phase 2: Backfill Data for Traceability
    print("\n📦 Phase 2: Backfilling Data...")
    with engine.connect() as conn:
        try:
            # 1. Backfill order_no for old orders
            print("Backfilling order_no...", end=" ", flush=True)
            conn.execute(text("UPDATE orders SET order_no = 'OLD-' || id WHERE order_no IS NULL;"))
            
            # 2. Backfill merchant_id for orphaned orders
            print("Backfilling merchant_id...", end=" ", flush=True)
            conn.execute(text("UPDATE orders SET merchant_id = (SELECT merchant_id FROM products WHERE products.id = orders.product_id) WHERE merchant_id IS NULL;"))
            
            conn.commit()
            print("✅ Done")
        except Exception as e:
            conn.rollback()
            print(f"❌ Error: {e}")

    print("\n✨ All fixes completed! Your old orders now have searchable IDs.")

if __name__ == "__main__":
    fix()
