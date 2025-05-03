
# 🏬 Multi-Store Inventory Backend (FastAPI)

This is a scalable, secure inventory backend system built with **FastAPI**, supporting thousands of stores and real-time stock management with audit logs, authentication, and Redis caching.

---

## ✅ Features

- RESTful API for Products, Stores, Stock Movements
- Auth secured (HTTP Basic)
- Async APIs with Background Tasks
- Redis-powered caching (optional)
- SQLite (read/write separation simulated)
- Audit logs for all stock actions
- Date-filtered reporting
- Rate limiting to avoid abuse

---

## 🧠 Design Decisions

| Decision | Why It Was Chosen |
|---------|--------------------|
| **FastAPI** | For speed, simplicity, and built-in async support |
| **SQLite** | Lightweight for local dev, replaceable with PostgreSQL |
| **Read/Write Separation** | Simulated via dual connections, prep for master/slave DBs |
| **Redis** | Optional caching for frequently accessed reads (like quantity checks) |
| **Background Tasks** | Simulates event-driven architecture for async stock writes |
| **Rate Limiting** | Prevents abuse and ensures fair usage |
| **Audit Logging** | Enables traceability and accountability for stock movements |

---

## 🤔 Assumptions

- Each product belongs to multiple stores (not 1:1).
- Quantity is tracked per (product_id, store_id).
- Stock movements can be `IN`, `OUT`, `SALE`, or `REMOVE`.
- API consumers are trusted after Basic Auth.
- Redis is optional (the app gracefully falls back to DB if Redis isn't available).

---

## 📦 API Design

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/add-product` | Add a new product (ID, name, category) |
| `POST` | `/add-store` | Add a new store |
| `POST` | `/stock` | Schedule a stock movement (event-driven) |
| `GET` | `/product/{product_id}/store/{store_id}/quantity` | View current stock level |
| `GET` | `/report/?store_id=&start_date=&end_date=` | Filtered report of movements |

All endpoints require Basic Auth (`admin` / `password123`).

---

## 🔁 Evolution Rationale (v1 → v3)

### ✅ **Stage 1** (v1):
- Basic product and stock movement support
- Flat DB operations, no stores or auth

### ✅ **Stage 2** (v2):
- Added store tracking
- Basic Auth
- Rate limiting
- Date filtering

### ✅ **Stage 3** (v3):
- Async endpoints with background task support
- Audit logs
- Redis caching
- Read/write separation
- Error-proof Redis fallback

---

## 🚀 How to Run
Run each stage's folder by keeping it on desktop and not in any folder

### Install Dependencies
```bash
pip install fastapi uvicorn slowapi redis python-multipart
```

### Run the App
```bash
python -m uvicorn main:app --reload
```

Then open: [http://localhost:8000/docs](http://localhost:8000/docs)

for stage 2 and 3:
Click **🔒 Authorize** → enter:
- Username: `admin`
- Password: `password123`

---

## 🧪 Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/add-product` | 10 requests/min |
| `/stock` | 20 requests/min |
| `/quantity`, `/report` | 20 requests/min |

---

## 📁 Directory Structure

```
📦 project/
 ┣ 📄 main.py
 ┣ 📄 README.md
 ┣ 📄 audit.log
 ┣ 📄 inventory.db
```

---