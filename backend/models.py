from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from database import Base
import datetime
import enum
import uuid

class DeliveryType(str, enum.Enum):
    LINK = "link"
    TEXT = "text"
    CODE = "code"

def generate_callback_key():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    callback_key = Column(String, default=generate_callback_key)
    merchant_email = Column(String, nullable=True) # The email they use to forward receipts
    alipay_uid = Column(String, nullable=True) # Alipay PID/UID for jump links
    points_balance = Column(Float, default=0.0) # Commission points (RMB)
    
    products = relationship("Product", back_populates="merchant")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    price = Column(Float)
    delivery_type = Column(String)  # link, text, code
    delivery_content = Column(String)
    qr_code_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    merchant = relationship("User", back_populates="products")
    orders = relationship("Order", back_populates="product")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    amount = Column(Float)  # Final amount including offset
    unique_offset = Column(Float, default=0.0)
    commission_fee = Column(Float, default=0.0)
    status = Column(String, default="pending")  # pending, paid, expired
    payment_source = Column(String, nullable=True) # email, app, manual
    buyer_note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)

    product = relationship("Product", back_populates="orders")
