
from fastapi import FastAPI, Depends, Request, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Literal
import sqlite3
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
import secrets
import logging
import json

# --- Optional Redis ---
try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    try:
        redis_client.ping()
        REDIS_AVAILABLE = True
    except redis.exceptions.ConnectionError:
        redis_client = None
        REDIS_AVAILABLE = False
except Exception:
    redis_client = None
    REDIS_AVAILABLE = False

# --- App, Security & Logging Setup ---
app = FastAPI()
security = HTTPBasic()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

logging.basicConfig(filename='audit.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# --- SQLite DB Read/Write Setup ---
write_conn = sqlite3.connect("inventory.db", check_same_thread=False)
read_conn = sqlite3.connect("inventory.db", check_same_thread=False)
write_cursor = write_conn.cursor()
read_cursor = read_conn.cursor()

# --- Initialize Tables ---
write_cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT,
    category TEXT
)
""")
write_cursor.execute("""
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY,
    name TEXT
)
""")
write_cursor.execute("""
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    store_id INTEGER,
    movement_type TEXT,
    quantity INTEGER,
    timestamp TEXT
)
""")
write_conn.commit()

# --- Basic Auth ---
USERNAME = "admin"
PASSWORD = "password123"

def verify_user(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username, USERNAME) and
            secrets.compare_digest(credentials.password, PASSWORD)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- Models ---
class Product(BaseModel):
    id: int
    name: str
    category: str

class Store(BaseModel):
    id: int
    name: str

class Movement(BaseModel):
    product_id: int
    store_id: int
    movement_type: Literal["IN", "SALE", "REMOVE", "OUT"]
    quantity: int

# --- Background Task ---
def record_stock_in_db(movement: Movement, user: str, ip: str):
    timestamp = datetime.now().isoformat()
    write_cursor.execute("""
        INSERT INTO stock_movements (product_id, store_id, movement_type, quantity, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (movement.product_id, movement.store_id, movement.movement_type, movement.quantity, timestamp))
    write_conn.commit()
    logging.info(f"User {ip} - {user} moved {movement.quantity} ({movement.movement_type}) for product {movement.product_id} in store {movement.store_id}")

    # Invalidate Redis cache
    if REDIS_AVAILABLE:
        try:
            cache_key = f"quantity:{movement.product_id}:{movement.store_id}"
            redis_client.delete(cache_key)
        except Exception as e:
            logging.warning(f"Redis delete failed: {e}")

# --- Routes ---
@app.post("/add-product")
@limiter.limit("10/minute")
async def add_product(request: Request, product: Product, user: str = Depends(verify_user)):
    write_cursor.execute("SELECT id FROM products WHERE id = ?", (product.id,))
    if write_cursor.fetchone():
        return {"error": "Product already exists."}
    write_cursor.execute("INSERT INTO products (id, name, category) VALUES (?, ?, ?)",
                         (product.id, product.name, product.category))
    write_conn.commit()
    return {"message": "Product added successfully"}

@app.post("/add-store")
@limiter.limit("10/minute")
async def add_store(request: Request, store: Store, user: str = Depends(verify_user)):
    write_cursor.execute("SELECT id FROM stores WHERE id = ?", (store.id,))
    if write_cursor.fetchone():
        return {"error": "Store already exists."}
    write_cursor.execute("INSERT INTO stores (id, name) VALUES (?, ?)", (store.id, store.name))
    write_conn.commit()
    return {"message": "Store added successfully"}

@app.post("/stock")
@limiter.limit("20/minute")
async def stock_movement(request: Request, movement: Movement, background_tasks: BackgroundTasks, user: str = Depends(verify_user)):
    write_cursor.execute("SELECT name FROM products WHERE id = ?", (movement.product_id,))
    if write_cursor.fetchone() is None:
        return {"error": "Product does not exist."}

    write_cursor.execute("SELECT name FROM stores WHERE id = ?", (movement.store_id,))
    if write_cursor.fetchone() is None:
        return {"error": "Store does not exist."}

    ip = get_remote_address(request)
    background_tasks.add_task(record_stock_in_db, movement, user, ip)
    return {"message": "Stock movement scheduled"}

@app.get("/product/{product_id}/store/{store_id}/quantity")
@limiter.limit("20/minute")
async def get_quantity(request: Request, product_id: int, store_id: int, user: str = Depends(verify_user)):
    cache_key = f"quantity:{product_id}:{store_id}"
    if REDIS_AVAILABLE:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logging.warning(f"Redis get failed: {e}")

    read_cursor.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product = read_cursor.fetchone()
    if not product:
        return {"error": "Product not found."}
    product_name = product[0]

    read_cursor.execute("""
        SELECT movement_type, quantity FROM stock_movements
        WHERE product_id = ? AND store_id = ?
    """, (product_id, store_id))
    rows = read_cursor.fetchall()
    quantity = 0
    for mtype, qty in rows:
        quantity += qty if mtype == "IN" else -qty

    result = {
        "product_id": product_id,
        "store_id": store_id,
        "product_name": product_name,
        "current_quantity": quantity
    }

    if REDIS_AVAILABLE:
        try:
            redis_client.set(cache_key, json.dumps(result), ex=60)
        except Exception as e:
            logging.warning(f"Redis set failed: {e}")

    return result

@app.get("/report/")
@limiter.limit("10/minute")
async def report(request: Request, store_id: int, start_date: str, end_date: str, user: str = Depends(verify_user)):
    read_cursor.execute("""
        SELECT sm.id, sm.product_id, p.name, sm.movement_type, sm.quantity, sm.timestamp
        FROM stock_movements sm
        JOIN products p ON sm.product_id = p.id
        WHERE sm.store_id = ? AND sm.timestamp BETWEEN ? AND ?
        ORDER BY sm.timestamp ASC
    """, (store_id, start_date, end_date))
    rows = read_cursor.fetchall()

    return {
        "store_id": store_id,
        "report": [
            {
                "movement_id": r[0],
                "product_id": r[1],
                "product_name": r[2],
                "type": r[3],
                "quantity": r[4],
                "timestamp": r[5]
            } for r in rows
        ]
    }
