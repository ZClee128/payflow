from sqlalchemy import text
from database import engine

def migrate():
    print("开始执行数据库迁移...")
    try:
        with engine.connect() as conn:
            # 增加 User 表的 callback_key
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS callback_key TEXT;"))
            # 增加 Order 表的 expires_at
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;"))
            conn.commit()
            print("✅ 数据库表结构更新成功！")
    except Exception as e:
        print(f"❌ 迁移失败: {e}")

if __name__ == "__main__":
    migrate()
