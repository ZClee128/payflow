import os
import re
import threading
import time
from imap_tools import MailBox, AND
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, text
from typing import List, Optional
import uuid
import imaplib
import email
from email.header import decode_header
from supabase import create_client, Client
from dotenv import load_dotenv
from passlib.context import CryptContext
from jose import JWTError, jwt
from contextlib import asynccontextmanager

# Support for Vercel deployment imports
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import models, database
from database import engine, get_db, SessionLocal

# Load environment variables
load_dotenv()

# Setup Security
SECRET_KEY = os.getenv("SECRET_KEY", "payflow-secure-secret-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Migration check: Ensure database is up to date with new billing fields
def run_migrations():
    with engine.connect() as conn:
        print("🔍 Checking database for newest features...")
        try:
            # Add columns if they don't exist
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_source VARCHAR;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS alipay_uid VARCHAR;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS points_balance FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superadmin BOOLEAN DEFAULT FALSE;"))
            
            # AUTO-GRANT SUPERADMIN TO THE OWNER
            conn.execute(text("UPDATE users SET is_superadmin = TRUE WHERE email = 'zclee520@gmail.com';"))
            
            conn.commit()
            print("✅ Database schema is up to date (Super Admin Enabled).")
        except Exception as e:
            print(f"ℹ️ Migration notice: {e}")

run_migrations()
models.Base.metadata.create_all(bind=engine)

# --- Shared Payment Processing Logic ---

def mark_order_as_paid(db: Session, merchant_id: int, amount: float, source: str = None):
    """
    Core payment confirmation logic.
    Deducts commission from merchant balance upon successful identification.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Find matching pending order for this merchant and exact amount
    order = db.query(models.Order).join(models.Product).filter(
        models.Product.merchant_id == merchant_id,
        models.Order.amount == amount,
        models.Order.status == "pending",
        models.Order.expires_at > now
    ).first()

    if order:
        order.status = "paid"
        order.paid_at = now
        order.payment_source = source
        
        # DEDUCT COMMISSION FROM MERCHANT BALANCE (Skip for superadmins)
        merchant = db.query(models.User).filter(models.User.id == merchant_id).first()
        if merchant:
            if merchant.is_superadmin:
                print(f"⭐️ SuperAdmin {merchant_id}: Skipping commission deduction.")
            else:
                merchant.points_balance = round(merchant.points_balance - order.commission_fee, 4)
                print(f"💰 Deducted ¥{order.commission_fee} commission from merchant {merchant_id}. Balance: ¥{merchant.points_balance}")
        
        db.commit()
        print(f"✅ Order #{order.id} marked as PAID via {source}.")
        return order
    return None

# --- Email Monitoring Worker ---

# --- Email Monitoring Wrapper ---

def check_emails_once():
    """
    Performs a single pass of the IMAP synchronization logic.
    Refactored for serverless compatibility.
    """
    IMAP_SERVER = os.getenv("IMAP_SERVER")
    IMAP_USER = os.getenv("IMAP_USER")
    IMAP_PASS = os.getenv("IMAP_PASS")

    if not all([IMAP_SERVER, IMAP_USER, IMAP_PASS]):
        return 0

    count = 0
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        # Handle 163 search ID tag
        tag = mail._new_tag().decode()
        mail.send(f'{tag} ID ("name" "client" "version" "1.0.0")\r\n'.encode())
        while True:
            line = mail.readline()
            if not line: break
            if tag.encode() in line: break
        
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("INBOX")
        status, messages = mail.search(None, "UNSEEN")
        if status == "OK":
            for num in messages[0].split():
                res, msg_data = mail.fetch(num, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        from_email = email.utils.parseaddr(msg.get("From"))[1]
                        subject, encoding = decode_header(msg.get("Subject"))[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8")
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload: body = payload.decode(errors="ignore")
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload: body = payload.decode(errors="ignore")

                        combined_text = subject + " " + body
                        match = re.search(r"(\d+\.\d{2})", combined_text)
                        if match:
                            amount = float(match.group(1))
                            db = SessionLocal()
                            merchant = db.query(models.User).filter(models.User.merchant_email == from_email).first()
                            if merchant:
                                order = mark_order_as_paid(db, merchant.id, amount, source="email")
                                if order: count += 1
                            db.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Email Sync Error: {e}")
    return count

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan manager for FastAPI. 
    Note: Background threads don't persist on Vercel, but we keep this for local dev.
    """
    yield

app = FastAPI(title="PayFlow API", lifespan=lifespan)

@app.get("/api/worker/check-emails")
async def trigger_email_check(token: str = Query(None)):
    """
    Endpoint to be triggered by a Cron Job (e.g. Vercel Cron or cron-job.org).
    Simple token check to prevent abuse.
    """
    if token != os.getenv("SECRET_KEY"):
         raise HTTPException(status_code=403, detail="Forbidden")
    
    count = check_emails_once()
    return {"status": "success", "processed_orders": count}

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# Supabase Storage Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BUCKET_NAME = "qrcodes"

supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Auth Utilities ---

def verify_password(plain_password, hashed_password): return pwd_context.verify(plain_password, hashed_password)
def get_password_hash(password): return pwd_context.hash(password)
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(models.User).filter(models.User.email == payload.get("sub")).first()
        if user: return user
    except: pass
    raise HTTPException(status_code=401, detail="Could not validate credentials")

# --- Routes ---

@app.post("/api/auth/register")
async def register(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    db.add(models.User(email=email, hashed_password=get_password_hash(password), points_balance=5.0))
    db.commit()
    return {"message": "User created successfully"}

@app.post("/api/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    print(f"🔑 Login Attempt: {form_data.username}")
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user:
        print(f"❌ Login Failed: User {form_data.username} not found")
        raise HTTPException(status_code=404, detail="账号不存在，请先注册")
    
    if not verify_password(form_data.password, user.hashed_password):
        print(f"❌ Login Failed: Incorrect password for {form_data.username}")
        raise HTTPException(status_code=401, detail="密码错误")
    
    print(f"✅ Login Success: {form_data.username}")
    return {"access_token": create_access_token(data={"sub": user.email}), "token_type": "bearer"}

@app.get("/api/merchants/{merchant_id}/info")
async def get_merchant_info(merchant_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == merchant_id).first()
    if not user: raise HTTPException(status_code=404, detail="Merchant not found")
    return {"email": user.email, "alipay_uid": user.alipay_uid}

@app.get("/api/merchants/{merchant_id}/products")
async def get_merchant_products(merchant_id: int, db: Session = Depends(get_db)):
    return db.query(models.Product).filter(models.Product.merchant_id == merchant_id).all()

@app.post("/api/products")
async def create_product(
    name: str = Form(...), price: float = Form(...), delivery_type: str = Form(...), 
    delivery_content: str = Form(...), description: Optional[str] = Form(None), 
    qr_code: UploadFile = File(...), db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    if not supabase: raise HTTPException(status_code=500, detail="Supabase not configured")
    file_ext = qr_code.filename.split(".")[-1]
    file_name = f"{uuid.uuid4()}.{file_ext}"
    contents = await qr_code.read()
    supabase.storage.from_(BUCKET_NAME).upload(path=file_name, file=contents, file_options={"content-type": qr_code.content_type})
    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(file_name)
    p = models.Product(merchant_id=current_user.id, name=name, price=price, delivery_type=delivery_type, delivery_content=delivery_content, description=description, qr_code_path=public_url)
    db.add(p); db.commit(); db.refresh(p)
    return p

@app.get("/api/products")
async def list_products(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Product).filter(models.Product.merchant_id == current_user.id).all()

@app.get("/api/products/{product_id}")
async def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not p: raise HTTPException(status_code=404, detail="Product not found")
    return {"id": p.id, "name": p.name, "price": p.price, "description": p.description, "qr_code_path": p.qr_code_path, "merchant_id": p.merchant_id}

@app.delete("/api/products/{product_id}")
async def delete_product(product_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id, models.Product.merchant_id == current_user.id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or unauthorized")
    
    db.delete(product)
    db.commit()
    return {"message": "Product deleted successfully"}

@app.post("/api/orders")
async def create_order(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product: raise HTTPException(status_code=404, detail="Product not found")
    
    # ... (skipping merchant balance check, etc for diff accuracy) ...
    # (re-pasting the full logic to ensure correctness)
    merchant = product.merchant
    # Super Admin Check: skip balance check
    if not merchant.is_superadmin:
        min_points_required = round(product.price * 0.01, 2)
        if merchant.points_balance < min_points_required:
             raise HTTPException(status_code=403, detail="Merchant balance too low. Please contact the administrator.")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Clean up expired orders first for this merchant
    product_ids = [p.id for p in merchant.products]
    db.query(models.Order).filter(models.Order.product_id.in_(product_ids), models.Order.status == "pending", models.Order.expires_at < now).update({models.Order.status: "expired"}, synchronize_session=False)
    db.commit()

    active_amounts = [round(o.amount, 2) for o in db.query(models.Order).join(models.Product).filter(models.Product.merchant_id == merchant.id, models.Order.status == "pending").all()]
    offset = 0.0
    final_amount = round(product.price + offset, 2)
    while final_amount in active_amounts:
        offset += 0.01
        final_amount = round(product.price + offset, 2)
    
    commission = round(product.price * 0.01, 2)
    db_order = models.Order(product_id=product_id, amount=final_amount, unique_offset=offset, commission_fee=commission, status="pending", expires_at=now + timedelta(minutes=5))
    db.add(db_order); db.commit()
    
    alipay_url = f"alipays://platformapi/startapp?appId=09999988&actionType=toAccount&goBack=NO&userId={merchant.alipay_uid}&amount={final_amount}" if merchant.alipay_uid else None
    
    # BRIDGE QR: Generate a QR that points to the dedicated pay.html site on mobile
    import urllib.parse
    base_url = str(request.base_url).rstrip('/')
    bridge_url = f"{base_url}/pay.html?order_id={db_order.id}"
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(bridge_url)}&margin=10"

    return {
        "order_id": db_order.id, "amount": db_order.amount, "qr_code": qr_code_url, 
        "status": db_order.status, "expires_in": 300, "alipay_url": alipay_url
    }

@app.get("/api/orders/{order_id}/status")
async def get_order_status(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    # Final fix for datetime comparison: Ensure order.expires_at is naive to match local comparison
    expires_at_naive = order.expires_at.replace(tzinfo=None) if order.expires_at.tzinfo else order.expires_at
    if order.status == "pending" and expires_at_naive < datetime.now(timezone.utc).replace(tzinfo=None):
        order.status = "expired"; db.commit()
    if order.status == "paid":
        return {"status": "paid", "content": order.product.delivery_content}
    return {"status": order.status}

@app.post("/api/orders/{order_id}/confirm")
async def confirm_payment(order_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order or order.product.merchant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if order.status != "paid":
        order.status = "paid"
        order.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)
        order.payment_source = "manual"
        if not current_user.is_superadmin:
            current_user.points_balance = round(current_user.points_balance - order.commission_fee, 4)
            print(f"💰 Manual Confirm: Deducted ¥{order.commission_fee} from {current_user.id}")
        db.commit()
    return {"status": "paid"}

@app.get("/api/orders/{order_id}/details")
async def get_order_details(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": order.id,
        "amount": order.amount,
        "status": order.status,
        "qr_code": order.product.qr_code_path,
        "alipay_url": f"alipays://platformapi/startapp?appId=09999988&actionType=toAccount&goBack=NO&userId={order.product.merchant.alipay_uid}&amount={order.amount}" if order.product.merchant.alipay_uid else None,
        "content": order.product.delivery_content if order.status == "paid" else None
    }

@app.post("/api/callback/notify")
async def payment_notify(amount: float = Query(...), key: str = Query(...), db: Session = Depends(get_db)):
    merchant = db.query(models.User).filter(models.User.callback_key == key).first()
    if not merchant: raise HTTPException(status_code=401, detail="Invalid key")
    order = mark_order_as_paid(db, merchant.id, amount, source="app")
    if order: return {"status": "success"}
    return {"status": "ignored"}

@app.get("/api/merchant/stats")
async def get_merchant_stats(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        # Robust query: fall back to a safer search if merchant_id column is problematic
        orders = db.query(models.Order).filter(models.Order.merchant_id == current_user.id).all()
        paid = [o for o in orders if o.status == "paid"]
        
        return {
            "total_sales": round(sum((o.amount or 0) for o in paid), 2),
            "total_commission": round(sum((o.commission_fee or 0) for o in paid), 2),
            "order_count": len(paid),
            "pending_orders": len([o for o in orders if o.status == "pending"]),
            "merchant_id": current_user.id,
            "callback_key": current_user.callback_key,
            "merchant_email": current_user.merchant_email,
            "alipay_uid": current_user.alipay_uid,
            "points_balance": round(current_user.points_balance, 2),
            "is_superadmin": current_user.is_superadmin
        }
    except Exception as e:
        print(f"❌ Stats error: {e}")
        return {
            "total_sales": 0, "order_count": 0, "pending_orders": 0,
            "points_balance": round(current_user.points_balance, 2),
            "is_superadmin": current_user.is_superadmin
        }

@app.post("/api/merchant/settings")
async def update_settings(merchant_email: Optional[str] = Form(None), alipay_uid: Optional[str] = Form(None), db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    current_user.merchant_email = merchant_email
    current_user.alipay_uid = alipay_uid
    db.commit()
    return {"status": "success"}

@app.get("/api/merchant/orders")
async def list_merchant_orders(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        orders = db.query(models.Order).filter(models.Order.merchant_id == current_user.id).order_by(models.Order.created_at.desc()).limit(50).all()
        return [{
            "id": o.id, 
            "order_no": o.order_no or f"ORD-{o.id}", 
            "product_name": o.product.name if o.product else "已删商品", 
            "amount": (o.amount or 0), 
            "net_profit": round((o.amount or 0) - (o.commission_fee or 0), 2),
            "status": o.status or "pending", 
            "source": o.payment_source or "manual", 
            "created_at": o.created_at.strftime("%H:%M:%S") if o.created_at else "--:--:--"
        } for o in orders]
    except Exception as e:
        print(f"❌ Order list error: {e}")
        return []

# Mount static files (Frontend) - ONLY in local development
# On Vercel, static files are handled by the edge network via vercel.json
if not os.getenv("VERCEL"):
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
    if os.path.exists(frontend_dir):
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
