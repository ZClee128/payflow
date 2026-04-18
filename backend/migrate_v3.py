from sqlalchemy import text
from database import engine

def migrate():
    print("开始执行数据库迁移 (v3)...")
    try:
        with engine.connect() as conn:
            # 增加 User 表的 merchant_email
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS merchant_email TEXT;"))
            conn.commit()
            print("✅ 数据库表结构更新成功！")
    except Exception as e:
        print(f"❌ 迁移失败: {e}")

if __name__ == "__main__":
    migrate()
