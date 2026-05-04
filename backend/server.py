from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
import json
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from io import BytesIO, StringIO
import csv
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from fpdf import FPDF
from fastapi import UploadFile, File

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)


def _resolve_db_name() -> str:
    """
    MongoDB database names cannot contain any of: / \\ . " $ * < > : | ?
    We sanitize/validate so a mis-configured DB_NAME env var (e.g. accidentally
    set to a full URL, domain, or password) does not crash backend startup.
    Falls back to 'app_db' if the configured name is unusable.
    """
    raw = (os.environ.get('DB_NAME') or '').strip()
    if not raw:
        return 'app_db'
    invalid_chars = set('/\\. "$*<>:|?')
    sanitized = ''.join('_' if ch in invalid_chars else ch for ch in raw)
    # After sanitizing, ensure non-empty and <=63 bytes per Mongo limit.
    sanitized = sanitized[:63].strip('_') or 'app_db'
    if sanitized != raw:
        logging.getLogger(__name__).warning(
            "DB_NAME '%s' contained invalid characters; using sanitized name '%s'",
            raw, sanitized,
        )
    return sanitized


db = client[_resolve_db_name()]

app = FastAPI()
api_router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

JWT_ALGORITHM = "HS256"

def get_jwt_secret():
    return os.environ["JWT_SECRET"]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=60), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def require_editor(request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "user"):
        raise HTTPException(status_code=403, detail="Edit access required")
    return user

# ---- AUTH ENDPOINTS ----
# Login rate limiter: max 5 failed attempts per (IP + email) in a 15-minute
# sliding window. Successful login resets the counter for that key.
_LOGIN_FAIL_WINDOW_SEC = 15 * 60
_LOGIN_FAIL_MAX = 5
_login_fails: dict = {}  # { (ip, email): [timestamps...] }

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _login_rate_check(key: tuple) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds). Prunes old entries."""
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - _LOGIN_FAIL_WINDOW_SEC
    attempts = [t for t in _login_fails.get(key, []) if t > cutoff]
    _login_fails[key] = attempts
    if len(attempts) >= _LOGIN_FAIL_MAX:
        retry_after = int(attempts[0] + _LOGIN_FAIL_WINDOW_SEC - now) + 1
        return False, max(retry_after, 1)
    return True, 0

@api_router.post("/auth/login")
async def login(request: Request, response: Response):
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    key = (_client_ip(request), email)

    allowed, retry_after = _login_rate_check(key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {retry_after // 60 + 1} minute(s).",
            headers={"Retry-After": str(retry_after)},
        )

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(password, user["password_hash"]):
        _login_fails.setdefault(key, []).append(datetime.now(timezone.utc).timestamp())
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Successful login: reset counter for this key
    _login_fails.pop(key, None)
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"id": user_id, "email": user["email"], "name": user.get("name", ""), "role": user.get("role", "user")}

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}

# ---- HEALTH CHECK ----
@api_router.get("/health")
async def health():
    """Public uptime probe. Returns 200 + db status, or 503 if DB is unreachable."""
    db_ok = False
    try:
        await client.admin.command("ping")
        db_ok = True
    except Exception as e:
        logger.warning(f"Health check DB ping failed: {e}")
    payload = {"status": "ok" if db_ok else "degraded", "db_ok": db_ok,
               "timestamp": datetime.now(timezone.utc).isoformat()}
    if not db_ok:
        return Response(content=json.dumps(payload), media_type="application/json", status_code=503)
    return payload

@api_router.get("/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    return user

@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access_token = create_access_token(str(user["_id"]), user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
        return {"message": "Token refreshed"}
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# ---- USER MANAGEMENT (Admin only) ----
@api_router.get("/users")
async def list_users(request: Request):
    await require_admin(request)
    users = await db.users.find({}).sort("created_at", -1).to_list(500)
    for u in users:
        u["id"] = str(u.pop("_id"))
        u.pop("password_hash", None)
    return users

@api_router.post("/users")
async def create_user(request: Request):
    await require_admin(request)
    body = await request.json()
    email = body.get("email", "").strip().lower()
    if not email or not body.get("password"):
        raise HTTPException(status_code=400, detail="Email and password required")
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    role = body.get("role", "viewer")
    if role not in ("admin", "user", "viewer"):
        role = "viewer"
    user = {
        "email": email,
        "password_hash": hash_password(body["password"]),
        "name": body.get("name", ""),
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.users.insert_one(user)
    user["id"] = str(result.inserted_id)
    user.pop("_id", None)
    user.pop("password_hash", None)
    return user

@api_router.put("/users/{user_id}")
async def update_user(user_id: str, request: Request):
    admin = await require_admin(request)
    body = await request.json()
    update = {}
    if "name" in body:
        update["name"] = body["name"]
    if "email" in body:
        new_email = body["email"].strip().lower()
        existing = await db.users.find_one({"email": new_email, "_id": {"$ne": ObjectId(user_id)}})
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")
        update["email"] = new_email
    if "role" in body and body["role"] in ("admin", "user", "viewer"):
        if user_id == str(admin["_id"]) and body["role"] != "admin":
            raise HTTPException(status_code=400, detail="Cannot demote yourself")
        update["role"] = body["role"]
    if "password" in body and body["password"]:
        update["password_hash"] = hash_password(body["password"])
    if update:
        await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update})
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["id"] = str(user.pop("_id"))
    user.pop("password_hash", None)
    return user

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    admin = await require_admin(request)
    if user_id == str(admin["_id"]):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}

# ---- EVENTS CRUD ----
@api_router.post("/events")
async def create_event(request: Request):
    await require_editor(request)
    body = await request.json()
    event = {
        "job_number": body.get("job_number", ""),
        "event_name": body.get("event_name", ""),
        "employer": body.get("employer", ""),
        "venue": body.get("venue", ""),
        "payroll_name": body.get("payroll_name", ""),
        "contact_email": body.get("contact_email", ""),
        "cell_phone": body.get("cell_phone", ""),
        "company_name": body.get("company_name", ""),
        "company_email": body.get("company_email", ""),
        "company_phone": body.get("company_phone", ""),
        "pay_period_start": body.get("pay_period_start", ""),
        "pay_period_end": body.get("pay_period_end", ""),
        "fund_pct": float(body.get("fund_pct", 0.02)),
        "benefit_pct": float(body.get("benefit_pct", 0.21)),
        "deduction_pct": float(body.get("deduction_pct", 0.05)),
        "days": body.get("days", {}),
        "notes": body.get("notes", {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.events.insert_one(event)
    event["id"] = str(result.inserted_id)
    event.pop("_id", None)
    return event

@api_router.get("/events")
async def list_events(request: Request):
    await get_current_user(request)
    events = await db.events.find({}).sort("created_at", -1).to_list(1000)
    for e in events:
        e["id"] = str(e.pop("_id"))
    return events

@api_router.get("/events/{event_id}")
async def get_event(event_id: str, request: Request):
    await get_current_user(request)
    event = await db.events.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event["id"] = str(event.pop("_id"))
    return event

@api_router.put("/events/{event_id}")
async def update_event(event_id: str, request: Request):
    await require_editor(request)
    body = await request.json()
    body.pop("id", None)
    body.pop("_id", None)
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "fund_pct" in body:
        body["fund_pct"] = float(body["fund_pct"])
    if "benefit_pct" in body:
        body["benefit_pct"] = float(body["benefit_pct"])
    if "deduction_pct" in body:
        body["deduction_pct"] = float(body["deduction_pct"])
    await db.events.update_one({"_id": ObjectId(event_id)}, {"$set": body})
    event = await db.events.find_one({"_id": ObjectId(event_id)})
    event["id"] = str(event.pop("_id"))
    return event

@api_router.delete("/events/{event_id}")
async def delete_event(event_id: str, request: Request):
    await require_editor(request)
    await db.events.delete_one({"_id": ObjectId(event_id)})
    await db.employees.delete_many({"event_id": event_id})
    await db.time_entries.delete_many({"event_id": event_id})
    return {"message": "Event deleted"}

@api_router.post("/events/{event_id}/clone")
async def clone_event(event_id: str, request: Request):
    await require_editor(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    src = await db.events.find_one({"_id": ObjectId(event_id)})
    if not src:
        raise HTTPException(status_code=404, detail="Event not found")

    # Build new event: copy metadata & rates, blank pay-period dates, day dates, notes.
    now_iso = datetime.now(timezone.utc).isoformat()
    new_event = {k: v for k, v in src.items() if k not in ("_id", "created_at", "updated_at", "days", "notes", "pay_period_start", "pay_period_end")}
    new_event["event_name"] = (body.get("event_name") or f"{src.get('event_name', '') or 'Event'} (Copy)").strip()
    new_event["pay_period_start"] = ""
    new_event["pay_period_end"] = ""
    new_event["days"] = {}
    new_event["notes"] = {}
    new_event["created_at"] = now_iso
    new_event["updated_at"] = now_iso
    result = await db.events.insert_one(new_event)
    new_id = str(result.inserted_id)

    # Copy employees with rates & sort_order. No time entries are copied (hours blanked).
    src_emps = await db.employees.find({"event_id": event_id}).sort("sort_order", 1).to_list(500)
    if src_emps:
        new_emps = [{
            "event_id": new_id,
            "name": e.get("name", ""),
            "dept_emp_num": e.get("dept_emp_num", ""),
            "rate1": float(e.get("rate1", 0) or 0),
            "rate2": float(e.get("rate2", 0) or 0),
            "special_rate": float(e.get("special_rate", 0) or 0),
            "sort_order": int(e.get("sort_order", i + 1)),
        } for i, e in enumerate(src_emps)]
        await db.employees.insert_many(new_emps)

    new_event["id"] = new_id
    new_event.pop("_id", None)
    return new_event

# ---- EMPLOYEES CRUD ----
@api_router.get("/events/{event_id}/employees")
async def list_employees(event_id: str, request: Request):
    await get_current_user(request)
    employees = await db.employees.find({"event_id": event_id}).sort("sort_order", 1).to_list(200)
    for e in employees:
        e["id"] = str(e.pop("_id"))
    return employees

@api_router.post("/events/{event_id}/employees")
async def add_employee(event_id: str, request: Request):
    await require_editor(request)
    body = await request.json()
    count = await db.employees.count_documents({"event_id": event_id})
    emp = {
        "event_id": event_id,
        "name": body.get("name", ""),
        "dept_emp_num": body.get("dept_emp_num", ""),
        "rate1": float(body.get("rate1", 0)),
        "rate2": float(body.get("rate2", 0)),
        "special_rate": float(body.get("special_rate", 0)),
        "sort_order": count + 1,
    }
    result = await db.employees.insert_one(emp)
    emp["id"] = str(result.inserted_id)
    emp.pop("_id", None)
    return emp

@api_router.put("/events/{event_id}/employees/{emp_id}")
async def update_employee(event_id: str, emp_id: str, request: Request):
    await require_editor(request)
    body = await request.json()
    update = {}
    for field in ["name", "dept_emp_num"]:
        if field in body:
            update[field] = body[field]
    for field in ["rate1", "rate2", "special_rate", "sort_order"]:
        if field in body:
            update[field] = float(body[field])
    if update:
        await db.employees.update_one({"_id": ObjectId(emp_id), "event_id": event_id}, {"$set": update})
    emp = await db.employees.find_one({"_id": ObjectId(emp_id)})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp["id"] = str(emp.pop("_id"))
    return emp

@api_router.delete("/events/{event_id}/employees/{emp_id}")
async def delete_employee(event_id: str, emp_id: str, request: Request):
    await require_editor(request)
    await db.employees.delete_one({"_id": ObjectId(emp_id), "event_id": event_id})
    await db.time_entries.delete_many({"event_id": event_id, "employee_id": emp_id})
    return {"message": "Employee deleted"}

# ---- EMPLOYEE REORDER ----
@api_router.post("/events/{event_id}/employees/reorder")
async def reorder_employees(event_id: str, request: Request):
    await require_editor(request)
    body = await request.json()
    order = body.get("order", [])
    for idx, emp_id in enumerate(order):
        await db.employees.update_one(
            {"_id": ObjectId(emp_id), "event_id": event_id},
            {"$set": {"sort_order": idx + 1}}
        )
    employees = await db.employees.find({"event_id": event_id}).sort("sort_order", 1).to_list(200)
    for e in employees:
        e["id"] = str(e.pop("_id"))
    return employees

# ---- IMPORT HELPERS ----
def _detect_columns(header):
    return {
        "name": next((i for i, h in enumerate(header) if 'name' in h), 0),
        "dept": next((i for i, h in enumerate(header) if 'dept' in h or 'emp' in h or 'number' in h), 1),
        "r1": next((i for i, h in enumerate(header) if 'rate' in h and '1' in h), 2),
        "r2": next((i for i, h in enumerate(header) if 'rate' in h and '2' in h), 3),
        "sr": next((i for i, h in enumerate(header) if 'special' in h or 'sr' in h), 4),
    }

def _safe_float(val):
    """Returns (value, error). error is None on success, otherwise a short message."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return 0.0, None
    try:
        return float(val), None
    except (ValueError, TypeError):
        return 0.0, f"could not parse '{val}' as a number"

def _validate_emp_row(row, cols, event_id, sort_order):
    """Returns (employee_dict | None, [warnings], error_message | None).
    None employee + error_message means skip the row. Warnings are non-fatal.
    """
    warnings: list = []

    # Skip totally empty rows silently
    if not any((c is not None and str(c).strip()) for c in row):
        return None, [], "empty row"

    # Required: Name
    name_val = row[cols["name"]] if len(row) > cols["name"] else None
    if not name_val or not str(name_val).strip():
        return None, [], "missing Name"
    name = str(name_val).strip()
    if len(name) > 200:
        warnings.append("Name truncated to 200 chars")
        name = name[:200]

    # Optional: dept/emp number (any string)
    dept_val = row[cols["dept"]] if len(row) > cols["dept"] else None
    dept = str(dept_val).strip() if dept_val is not None and str(dept_val).strip() else ""

    # Rates: must be numbers, default to 0 if blank, error if non-numeric
    r1, e1 = _safe_float(row[cols["r1"]] if len(row) > cols["r1"] else None)
    r2, e2 = _safe_float(row[cols["r2"]] if len(row) > cols["r2"] else None)
    sr, esr = _safe_float(row[cols["sr"]] if len(row) > cols["sr"] else None)
    for label, err in [("Rate 1", e1), ("Rate 2", e2), ("Special Rate", esr)]:
        if err:
            return None, warnings, f"{label}: {err}"
    for label, val in [("Rate 1", r1), ("Rate 2", r2), ("Special Rate", sr)]:
        if val < 0:
            return None, warnings, f"{label} cannot be negative ({val})"
        if val > 10000:
            warnings.append(f"{label} unusually high ({val})")

    return {
        "event_id": event_id,
        "name": name,
        "dept_emp_num": dept,
        "rate1": r1,
        "rate2": r2,
        "special_rate": sr,
        "sort_order": sort_order,
    }, warnings, None

# ---- BULK EMPLOYEE IMPORT ----
@api_router.post("/events/{event_id}/employees/import")
async def import_employees(event_id: str, request: Request, file: UploadFile = File(...)):
    await require_editor(request)
    content = await file.read()
    filename = file.filename or ""
    imported: list = []
    errors: list = []     # rows skipped with reason
    warnings: list = []   # rows imported with caveats
    count = await db.employees.count_documents({"event_id": event_id})

    def _ingest_rows(raw_rows):
        nonlocal count
        if not raw_rows:
            return [], _detect_columns([])
        header = [str(c).strip().lower() if c is not None else "" for c in raw_rows[0]]
        cols = _detect_columns(header)
        return raw_rows[1:], cols

    try:
        if filename.endswith(('.xlsx', '.xls')):
            wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
            ws = wb.active
            raw_rows = [list(r) for r in ws.iter_rows(values_only=True)]
        else:
            text = content.decode('utf-8-sig', errors='replace')
            reader = csv.reader(StringIO(text))
            raw_rows = [list(r) for r in reader]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    data_rows, cols = _ingest_rows(raw_rows)

    for idx, row in enumerate(data_rows, start=2):  # row 1 is header, so data starts at row 2
        emp, row_warnings, err = _validate_emp_row(row, cols, event_id, count + 1)
        if err == "empty row":
            continue
        if err:
            errors.append({"row": idx, "name": _safe_row_name(row, cols), "reason": err})
            continue
        count += 1
        result = await db.employees.insert_one(emp)
        emp["id"] = str(result.inserted_id)
        emp.pop("_id", None)
        imported.append(emp)
        for w in row_warnings:
            warnings.append({"row": idx, "name": emp["name"], "reason": w})

    return {
        "imported": len(imported),
        "skipped": len(errors),
        "employees": imported,
        "errors": errors,
        "warnings": warnings,
    }

def _safe_row_name(row, cols):
    try:
        v = row[cols["name"]]
        return str(v).strip() if v is not None else ""
    except (IndexError, KeyError, TypeError):
        return ""

# ---- TIME ENTRIES ----
@api_router.get("/events/{event_id}/time-entries")
async def get_time_entries(event_id: str, day: int, request: Request):
    await get_current_user(request)
    entries = await db.time_entries.find({"event_id": event_id, "day_number": day}).to_list(200)
    for e in entries:
        e["id"] = str(e.pop("_id"))
    return entries

@api_router.post("/events/{event_id}/time-entries/batch")
async def batch_update_time_entries(event_id: str, request: Request):
    await require_admin(request)
    body = await request.json()
    entries = body.get("entries", [])

    # Validate: an employee cannot have hours in BOTH Rate 1 and Rate 2 on the same day.
    employees = await db.employees.find({"event_id": event_id}).to_list(500)
    name_by_id = {str(e["_id"]): e.get("name", "") for e in employees}
    conflicts = []
    for entry in entries:
        r1_total = float(entry.get("st_r1", 0) or 0) + float(entry.get("ot_r1", 0) or 0) + float(entry.get("dt_r1", 0) or 0)
        r2_total = float(entry.get("st_r2", 0) or 0) + float(entry.get("ot_r2", 0) or 0) + float(entry.get("dt_r2", 0) or 0)
        if r1_total > 0 and r2_total > 0:
            conflicts.append(name_by_id.get(entry.get("employee_id"), entry.get("employee_id", "?")))
    if conflicts:
        names = ", ".join(conflicts[:5]) + ("..." if len(conflicts) > 5 else "")
        raise HTTPException(
            status_code=400,
            detail=f"{len(conflicts)} employee(s) have hours in BOTH Rate 1 and Rate 2 on this day: {names}. Use only one rate per employee per day.",
        )

    for entry in entries:
        emp_id = entry.get("employee_id")
        day_num = entry.get("day_number")
        update = {
            "event_id": event_id,
            "employee_id": emp_id,
            "day_number": day_num,
            "st_r1": float(entry.get("st_r1", 0)),
            "ot_r1": float(entry.get("ot_r1", 0)),
            "dt_r1": float(entry.get("dt_r1", 0)),
            "st_r2": float(entry.get("st_r2", 0)),
            "ot_r2": float(entry.get("ot_r2", 0)),
            "dt_r2": float(entry.get("dt_r2", 0)),
            "sr_hours": float(entry.get("sr_hours", 0)),
        }
        await db.time_entries.update_one(
            {"event_id": event_id, "employee_id": emp_id, "day_number": day_num},
            {"$set": update},
            upsert=True
        )
    return {"message": f"Updated {len(entries)} entries"}

# ---- CALCULATIONS ----
def calc_gross(rate1, rate2, special_rate, st_r1=0, ot_r1=0, dt_r1=0, st_r2=0, ot_r2=0, dt_r2=0, sr_hours=0):
    if (st_r1 + ot_r1 + dt_r1) == 0:
        return (rate2 * st_r2) + (rate2 * 1.5 * ot_r2) + (rate2 * 2 * dt_r2) + (special_rate * sr_hours)
    return (rate1 * st_r1) + (rate1 * 1.5 * ot_r1) + (rate1 * 2 * dt_r1) + (special_rate * sr_hours)

def calc_gross_from_entry(rate1, rate2, special_rate, entry):
    """Convenience wrapper that extracts hours from a time entry dict."""
    return calc_gross(rate1, rate2, special_rate,
                      entry.get("st_r1", 0), entry.get("ot_r1", 0), entry.get("dt_r1", 0),
                      entry.get("st_r2", 0), entry.get("ot_r2", 0), entry.get("dt_r2", 0),
                      entry.get("sr_hours", 0))

# ---- DAILY STATEMENT ----
@api_router.get("/events/{event_id}/daily-statement/{day}")
async def get_daily_statement(event_id: str, day: int, request: Request):
    await get_current_user(request)
    event = await db.events.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    employees = await db.employees.find({"event_id": event_id}).sort("sort_order", 1).to_list(200)
    entries = await db.time_entries.find({"event_id": event_id, "day_number": day}).to_list(200)
    entry_map = {e["employee_id"]: e for e in entries}
    fp, bp, dp = event.get("fund_pct", 0.02), event.get("benefit_pct", 0.21), event.get("deduction_pct", 0.05)
    result = []
    for emp in employees:
        eid = str(emp["_id"])
        te = entry_map.get(eid, {})
        s1, o1, d1 = te.get("st_r1", 0), te.get("ot_r1", 0), te.get("dt_r1", 0)
        s2, o2, d2 = te.get("st_r2", 0), te.get("ot_r2", 0), te.get("dt_r2", 0)
        sr = te.get("sr_hours", 0)
        r1, r2, spr = emp.get("rate1", 0), emp.get("rate2", 0), emp.get("special_rate", 0)
        gross = round(calc_gross(r1, r2, spr, s1, o1, d1, s2, o2, d2, sr), 2)
        total_hrs = s1 + o1 + d1 + s2 + o2 + d2
        has_r1 = (s1 + o1 + d1) > 0
        result.append({
            "employee_id": eid, "name": emp.get("name", ""), "dept_emp_num": emp.get("dept_emp_num", ""),
            "hrly_rate": r1 if has_r1 else r2,
            "st_hrs": s1 if has_r1 else s2, "ot_hrs": o1 if has_r1 else o2, "dt_hrs": d1 if has_r1 else d2,
            "special_rate": spr, "sr_hours": sr, "special_tot": round(spr * sr, 2),
            "total_hours": total_hrs, "gross": gross,
            "benefit_co": round(bp * gross, 2), "fund_co": round(fp * gross, 2), "deduction": round(dp * gross, 2),
            "used_r2": not has_r1 and (s2 + o2 + d2) > 0,
        })
    return {"day": day, "fund_pct": fp, "benefit_pct": bp, "deduction_pct": dp, "employees": result,
            "event_name": event.get("event_name",""), "employer": event.get("employer",""),
            "venue": event.get("venue",""), "job_number": event.get("job_number",""),
            "day_date": (event.get("days") or {}).get(str(day), {}).get("date", ""),
            "day_note": (event.get("notes") or {}).get(str(day), ""),
            "company_name": event.get("company_name", ""),
            "company_email": event.get("company_email", ""),
            "company_phone": event.get("company_phone", ""),
            "pay_period_start": event.get("pay_period_start", ""),
            "pay_period_end": event.get("pay_period_end", "")}

# ---- DAILY STATEMENT PDF ----
@api_router.get("/events/{event_id}/daily-statement/{day}/pdf")
async def export_daily_statement_pdf(event_id: str, day: int, request: Request):
    await get_current_user(request)
    stmt = await get_daily_statement(event_id, day, request)
    emps = [e for e in stmt["employees"] if e["total_hours"] > 0 or e["sr_hours"] > 0]

    pdf = FPDF(orientation='L', unit='in', format='Letter')
    pdf.set_auto_page_break(auto=True, margin=0.5)
    pdf.add_page()
    pw = 11 - 1.0
    pdf.set_left_margin(0.5)
    pdf.set_right_margin(0.5)

    # Company branding - left header
    if stmt.get('company_name'):
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(pw, 0.3, stmt['company_name'], new_x="LMARGIN", new_y="NEXT")
        brand_line = []
        if stmt.get('company_email'):
            brand_line.append(stmt['company_email'])
        if stmt.get('company_phone'):
            brand_line.append(stmt['company_phone'])
        if brand_line:
            pdf.set_font('Helvetica', '', 8)
            pdf.cell(pw, 0.2, "  |  ".join(brand_line), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.1)

    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(pw, 0.35, f"Daily Statement - Day {day}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(pw, 0.25, stmt.get("event_name", ""), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 9)
    info_parts = [f"Employer: {stmt.get('employer','')}",  f"Venue: {stmt.get('venue','')}",
                  f"Job #: {stmt.get('job_number','')}"]
    if stmt.get("day_date"):
        info_parts.append(f"Date: {stmt['day_date']}")
    pdf.cell(pw, 0.22, "  |  ".join(info_parts), new_x="LMARGIN", new_y="NEXT")
    if stmt.get("day_note"):
        pdf.set_font('Helvetica', 'I', 8)
        pdf.cell(pw, 0.2, f"Note: {stmt['day_note']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(pw, 0.2, f"Fund: {stmt['fund_pct']*100:.1f}%  |  Benefit: {stmt['benefit_pct']*100:.1f}%  |  Deduction: {stmt['deduction_pct']*100:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.1)

    headers = ["#", "Employee", "Dept/Emp #", "Hrly Rate", "S.T. Hrs", "O.T. Hrs", "D.T. Hrs",
               "Special Rate", "SR Hrs", "Special Tot", "Total Hrs", "Benefit", "Fund", "Deduct", "Gross Salary"]
    widths = [0.3, 1.4, 0.75, 0.6, 0.55, 0.55, 0.55, 0.65, 0.5, 0.6, 0.55, 0.65, 0.55, 0.55, 0.8]
    rh = 0.22

    pdf.set_font('Helvetica', 'B', 7.5)
    pdf.set_fill_color(230, 235, 245)
    pdf.set_draw_color(180, 180, 180)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], rh, h, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 7.5)
    r2_stmt_cols = {3, 4, 5, 6}  # Hrly Rate, S.T., O.T., D.T.
    for idx, emp in enumerate(emps):
        if pdf.get_y() > 7.5:
            pdf.add_page()
            pdf.set_font('Helvetica', 'B', 7.5)
            pdf.set_fill_color(230, 235, 245)
            for i, h in enumerate(headers):
                pdf.cell(widths[i], rh, h, border=1, fill=True, align='C')
            pdf.ln()
            pdf.set_font('Helvetica', '', 7.5)
        used_r2 = emp.get("used_r2", False)
        vals = [str(idx+1), emp["name"][:22], emp["dept_emp_num"][:12],
                f"${emp['hrly_rate']:.2f}",
                f"{emp['st_hrs']:.1f}" if emp['st_hrs'] else "-",
                f"{emp['ot_hrs']:.1f}" if emp['ot_hrs'] else "-",
                f"{emp['dt_hrs']:.1f}" if emp['dt_hrs'] else "-",
                f"${emp['special_rate']:.2f}" if emp['special_rate'] else "-",
                f"{emp['sr_hours']:.1f}" if emp['sr_hours'] else "-",
                f"${emp['special_tot']:.2f}" if emp['special_tot'] else "-",
                f"{emp['total_hours']:.1f}", f"${emp['benefit_co']:.2f}",
                f"${emp['fund_co']:.2f}", f"${emp['deduction']:.2f}", f"${emp['gross']:.2f}"]
        for i, v in enumerate(vals):
            align = 'L' if i <= 2 else 'R'
            if used_r2 and i in r2_stmt_cols:
                pdf.set_fill_color(255, 243, 224)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            elif idx % 2 == 1:
                pdf.set_fill_color(245, 247, 250)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            else:
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=False)
        pdf.ln()

    # Totals
    t_gross = sum(e['gross'] for e in emps)
    t_benefit = sum(e['benefit_co'] for e in emps)
    t_fund = sum(e['fund_co'] for e in emps)
    t_deduct = sum(e['deduction'] for e in emps)
    pdf.set_font('Helvetica', 'B', 7.5)
    pdf.set_fill_color(220, 225, 240)
    tots = ["", "TOTALS", "", "",
            f"{sum(e['st_hrs'] for e in emps):.1f}", f"{sum(e['ot_hrs'] for e in emps):.1f}",
            f"{sum(e['dt_hrs'] for e in emps):.1f}", "",
            f"{sum(e['sr_hours'] for e in emps):.1f}", f"${sum(e['special_tot'] for e in emps):.2f}",
            f"{sum(e['total_hours'] for e in emps):.1f}", f"${t_benefit:.2f}",
            f"${t_fund:.2f}", f"${t_deduct:.2f}", f"${t_gross:.2f}"]
    for i, v in enumerate(tots):
        align = 'L' if i <= 2 else 'R'
        pdf.cell(widths[i], rh + 0.03, v, border=1, align=align, fill=True)
    pdf.ln()
    # Grand Total box
    _pdf_grand_total_box(pdf, pw, t_gross, t_benefit, t_fund, t_deduct)
    pdf.ln(0.15)
    pdf.set_font('Helvetica', 'I', 7)
    pdf.cell(pw, 0.18, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    pdf_bytes = pdf.output()
    output = BytesIO(pdf_bytes)
    name = stmt.get("event_name", "") or "payroll"
    return StreamingResponse(output, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{name}_day{day}_statement.pdf"'})

# ---- GRAND TOTAL BOX HELPER (5 horizontal columns) ----
def _pdf_grand_total_box(pdf, pw, t_gross, t_benefit, t_fund, t_deduct):
    gt = t_gross + t_benefit + t_fund + t_deduct
    pdf.ln(0.2)
    pdf.set_draw_color(180, 180, 180)
    cw = pw / 5  # 5 equal columns

    # Labels row
    pdf.set_fill_color(240, 242, 248)
    pdf.set_font('Helvetica', 'B', 7.5)
    for label in ["Gross Salary", "Benefits", "Fund", "Deductions", "Grand Total"]:
        pdf.cell(cw, 0.22, label, border=1, fill=True, align='C')
    pdf.ln()

    # Values row
    pdf.set_font('Helvetica', '', 9)
    for i, val in enumerate([t_gross, t_benefit, t_fund, t_deduct, gt]):
        if i == 4:
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_fill_color(220, 225, 240)
            pdf.cell(cw, 0.3, f"${val:,.2f}", border=1, fill=True, align='C')
        else:
            pdf.cell(cw, 0.3, f"${val:,.2f}", border=1, align='C')
    pdf.ln()

# ---- COMBINED FULL REPORT PDF ----
def _pdf_company_branding(pdf, pw, co):
    if co.get('company_name'):
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(pw, 0.3, co['company_name'], new_x="LMARGIN", new_y="NEXT")
        parts = []
        if co.get('company_email'):
            parts.append(co['company_email'])
        if co.get('company_phone'):
            parts.append(co['company_phone'])
        if parts:
            pdf.set_font('Helvetica', '', 8)
            pdf.cell(pw, 0.2, "  |  ".join(parts), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.1)
    pp_start = co.get('pay_period_start', '')
    pp_end = co.get('pay_period_end', '')
    if pp_start or pp_end:
        pdf.set_font('Helvetica', '', 8)
        pp_label = "Pay Period: "
        if pp_start and pp_end:
            pp_label += f"{pp_start} to {pp_end}"
        elif pp_start:
            pp_label += f"Starting {pp_start}"
        else:
            pp_label += f"Ending {pp_end}"
        pdf.cell(pw, 0.2, pp_label, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.05)

def _pdf_daily_stmt_page(pdf, pw, stmt, day):
    rh = 0.22
    r2_cols = {3, 4, 5, 6}
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(pw, 0.3, f"Daily Statement - Day {day}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(pw, 0.22, stmt.get("event_name", ""), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 8)
    info = [f"Employer: {stmt.get('employer','')}",  f"Venue: {stmt.get('venue','')}",
            f"Job #: {stmt.get('job_number','')}"]
    if stmt.get("day_date"):
        info.append(f"Date: {stmt['day_date']}")
    pdf.cell(pw, 0.2, "  |  ".join(info), new_x="LMARGIN", new_y="NEXT")
    if stmt.get("day_note"):
        pdf.set_font('Helvetica', 'I', 7)
        pdf.cell(pw, 0.18, f"Note: {stmt['day_note']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 7)
    pdf.cell(pw, 0.18, f"Fund: {stmt['fund_pct']*100:.1f}%  |  Benefit: {stmt['benefit_pct']*100:.1f}%  |  Deduction: {stmt['deduction_pct']*100:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.08)

    headers = ["#", "Employee", "Dept/Emp #", "Hrly Rate", "S.T. Hrs", "O.T. Hrs", "D.T. Hrs",
               "Special Rate", "SR Hrs", "Special Tot", "Total Hrs", "Benefit", "Fund", "Deduct", "Gross Salary"]
    widths = [0.3, 1.4, 0.75, 0.6, 0.55, 0.55, 0.55, 0.65, 0.5, 0.6, 0.55, 0.65, 0.55, 0.55, 0.8]

    def _draw_stmt_headers():
        pdf.set_font('Helvetica', 'B', 7)
        pdf.set_draw_color(180, 180, 180)
        pdf.set_fill_color(230, 235, 245)
        for i, h in enumerate(headers):
            pdf.cell(widths[i], rh, h, border=1, fill=True, align='C')
        pdf.ln()

    _draw_stmt_headers()
    emps = [e for e in stmt["employees"] if e["total_hours"] > 0 or e["sr_hours"] > 0]
    pdf.set_font('Helvetica', '', 7)
    for idx, emp in enumerate(emps):
        if pdf.get_y() > 7.5:
            pdf.add_page()
            _pdf_company_branding(pdf, pw, stmt)
            _draw_stmt_headers()
            pdf.set_font('Helvetica', '', 7)
        used_r2 = emp.get("used_r2", False)
        vals = [str(idx+1), emp["name"][:22], emp["dept_emp_num"][:12],
                f"${emp['hrly_rate']:.2f}",
                f"{emp['st_hrs']:.1f}" if emp['st_hrs'] else "-",
                f"{emp['ot_hrs']:.1f}" if emp['ot_hrs'] else "-",
                f"{emp['dt_hrs']:.1f}" if emp['dt_hrs'] else "-",
                f"${emp['special_rate']:.2f}" if emp['special_rate'] else "-",
                f"{emp['sr_hours']:.1f}" if emp['sr_hours'] else "-",
                f"${emp['special_tot']:.2f}" if emp['special_tot'] else "-",
                f"{emp['total_hours']:.1f}", f"${emp['benefit_co']:.2f}",
                f"${emp['fund_co']:.2f}", f"${emp['deduction']:.2f}", f"${emp['gross']:.2f}"]
        for i, v in enumerate(vals):
            align = 'L' if i <= 2 else 'R'
            if used_r2 and i in r2_cols:
                pdf.set_fill_color(255, 243, 224)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            elif idx % 2 == 1:
                pdf.set_fill_color(245, 247, 250)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            else:
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=False)
        pdf.ln()
    # Totals
    if emps:
        t_gross = sum(e['gross'] for e in emps)
        t_benefit = sum(e['benefit_co'] for e in emps)
        t_fund = sum(e['fund_co'] for e in emps)
        t_deduct = sum(e['deduction'] for e in emps)
        pdf.set_font('Helvetica', 'B', 7)
        pdf.set_fill_color(220, 225, 240)
        tots = ["", "TOTALS", "", "",
                f"{sum(e['st_hrs'] for e in emps):.1f}", f"{sum(e['ot_hrs'] for e in emps):.1f}",
                f"{sum(e['dt_hrs'] for e in emps):.1f}", "",
                f"{sum(e['sr_hours'] for e in emps):.1f}", f"${sum(e['special_tot'] for e in emps):.2f}",
                f"{sum(e['total_hours'] for e in emps):.1f}", f"${t_benefit:.2f}",
                f"${t_fund:.2f}", f"${t_deduct:.2f}", f"${t_gross:.2f}"]
        for i, v in enumerate(tots):
            pdf.cell(widths[i], rh + 0.03, v, border=1, align='L' if i <= 2 else 'R', fill=True)
        pdf.ln()
        _pdf_grand_total_box(pdf, pw, t_gross, t_benefit, t_fund, t_deduct)

def _pdf_summary_page(pdf, pw, data):
    rh = 0.22
    r2_cols = {7, 8, 9, 10}
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(pw, 0.3, "Payroll Summary - All Days", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(pw, 0.22, f"{data['event']['event_name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(pw/3, 0.2, f"Employer: {data['event']['employer']}")
    pdf.cell(pw/3, 0.2, f"Venue: {data['event']['venue']}")
    pdf.cell(pw/3, 0.2, f"Job #: {data['event']['job_number']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 7)
    pdf.cell(pw, 0.18, f"Fund: {data['fund_pct']*100:.1f}%  |  Benefit: {data['benefit_pct']*100:.1f}%  |  Deduction: {data['deduction_pct']*100:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.08)

    headers = ["#", "Employee", "Dept#", "Rate 1", "R1 ST", "R1 OT", "R1 DT", "Rate 2",
               "R2 ST", "R2 OT", "R2 DT", "SR Rate", "SR Hrs", "SR Tot", "Tot Hrs",
               "Benefit", "Fund", "Deduct", "Gross Total"]
    widths = [0.3, 1.2, 0.65, 0.5, 0.45, 0.45, 0.45, 0.5,
              0.45, 0.45, 0.45, 0.5, 0.42, 0.52, 0.48, 0.58, 0.5, 0.5, 0.73]

    def _draw_sum_headers():
        pdf.set_font('Helvetica', 'B', 7)
        pdf.set_draw_color(180, 180, 180)
        for i, h in enumerate(headers):
            if i in r2_cols:
                pdf.set_fill_color(255, 224, 178)
            else:
                pdf.set_fill_color(230, 235, 245)
            pdf.cell(widths[i], rh, h, border=1, fill=True, align='C')
        pdf.ln()

    _draw_sum_headers()
    pdf.set_font('Helvetica', '', 7)
    emps = data["employees"]
    for idx, emp in enumerate(emps):
        if pdf.get_y() > 7.5:
            pdf.add_page()
            _pdf_company_branding(pdf, pw, data['event'])
            _draw_sum_headers()
            pdf.set_font('Helvetica', '', 7)
        vals = [str(idx+1), emp["name"][:18], emp["dept_emp_num"][:10],
                f"${emp['rate1']:.2f}", f"{emp['r1_st']:.1f}", f"{emp['r1_ot']:.1f}", f"{emp['r1_dt']:.1f}",
                f"${emp['rate2']:.2f}", f"{emp['r2_st']:.1f}", f"{emp['r2_ot']:.1f}", f"{emp['r2_dt']:.1f}",
                f"${emp['special_rate']:.2f}", f"{emp['sr_hours']:.1f}", f"${emp['special_tot']:.2f}",
                f"{emp['total_hours']:.1f}", f"${emp['benefit_co']:.2f}", f"${emp['fund_co']:.2f}",
                f"${emp['deduction']:.2f}", f"${emp['gross']:.2f}"]
        for i, v in enumerate(vals):
            align = 'L' if i <= 2 else 'R'
            if i in r2_cols:
                pdf.set_fill_color(255, 243, 224)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            elif idx % 2 == 1:
                pdf.set_fill_color(245, 247, 250)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            else:
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=False)
        pdf.ln()
    # Summary totals
    if emps:
        t_gross = sum(e['gross'] for e in emps)
        t_benefit = sum(e['benefit_co'] for e in emps)
        t_fund = sum(e['fund_co'] for e in emps)
        t_deduct = sum(e['deduction'] for e in emps)
        pdf.set_font('Helvetica', 'B', 7)
        tot = ["", "TOTALS", "",
               "", f"{sum(e['r1_st'] for e in emps):.1f}", f"{sum(e['r1_ot'] for e in emps):.1f}",
               f"{sum(e['r1_dt'] for e in emps):.1f}", "",
               f"{sum(e['r2_st'] for e in emps):.1f}", f"{sum(e['r2_ot'] for e in emps):.1f}",
               f"{sum(e['r2_dt'] for e in emps):.1f}", "",
               f"{sum(e['sr_hours'] for e in emps):.1f}", f"${sum(e['special_tot'] for e in emps):.2f}",
               f"{sum(e['total_hours'] for e in emps):.1f}", f"${t_benefit:.2f}",
               f"${t_fund:.2f}", f"${t_deduct:.2f}", f"${t_gross:.2f}"]
        for i, v in enumerate(tot):
            if i in r2_cols:
                pdf.set_fill_color(255, 236, 200)
            else:
                pdf.set_fill_color(220, 225, 240)
            pdf.cell(widths[i], rh + 0.03, v, border=1, align='L' if i <= 2 else 'R', fill=True)
        pdf.ln()
        _pdf_grand_total_box(pdf, pw, t_gross, t_benefit, t_fund, t_deduct)

@api_router.get("/events/{event_id}/export/full-pdf")
async def export_full_pdf(event_id: str, request: Request):
    await get_current_user(request)
    sum_data = await _get_sum_totals_data(event_id)
    # Hide employees with no hours entered yet from the full report
    sum_data = {**sum_data, "employees": [e for e in sum_data["employees"] if (e.get("total_hours") or 0) > 0]}
    co = sum_data['event']
    pw = 11 - 1.0

    pdf = FPDF(orientation='L', unit='in', format='Letter')
    pdf.set_auto_page_break(auto=True, margin=0.5)

    # --- Cover / Title page ---
    pdf.add_page()
    pdf.set_left_margin(0.5)
    pdf.set_right_margin(0.5)
    _pdf_company_branding(pdf, pw, co)
    pdf.ln(0.3)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.cell(pw, 0.5, "Full Payroll Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 14)
    pdf.cell(pw, 0.35, co.get('event_name', ''), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.15)
    pdf.set_font('Helvetica', '', 10)
    for label, val in [("Employer", co.get('employer','')), ("Venue", co.get('venue','')),
                       ("Job #", co.get('job_number','')), ("Payroll", co.get('payroll_name',''))]:
        if val:
            pdf.cell(pw, 0.25, f"{label}: {val}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.15)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(pw, 0.22, f"Fund: {sum_data['fund_pct']*100:.1f}%  |  Benefit: {sum_data['benefit_pct']*100:.1f}%  |  Deduction: {sum_data['deduction_pct']*100:.1f}%", new_x="LMARGIN", new_y="NEXT")

    # Table of contents
    pdf.ln(0.3)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(pw, 0.3, "Contents", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 9)

    # Determine which days have data
    days_with_data = []
    for day_num in range(1, 11):
        count = await db.time_entries.count_documents({"event_id": event_id, "day_number": day_num})
        if count > 0:
            day_date = (co.get('days') or {}).get(str(day_num), {}).get('date', '')
            days_with_data.append((day_num, day_date))
            label = f"Day {day_num}" + (f" - {day_date}" if day_date else "")
            pdf.cell(pw, 0.22, f"  {label}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pw, 0.22, "  Summary - All Days", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.1)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.cell(pw, 0.2, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  |  {len(days_with_data)} day(s)  |  {len(sum_data['employees'])} employee(s)")

    # --- Daily statement pages ---
    for day_num, day_date in days_with_data:
        pdf.add_page()
        pdf.set_left_margin(0.5)
        pdf.set_right_margin(0.5)
        _pdf_company_branding(pdf, pw, co)
        stmt = await get_daily_statement(event_id, day_num, request)
        # Hide employees with zero hours on this particular day
        stmt = {**stmt, "employees": [e for e in stmt["employees"] if (e.get("total_hours") or 0) > 0 or (e.get("sr_hours") or 0) > 0]}
        _pdf_daily_stmt_page(pdf, pw, stmt, day_num)

    # --- Summary page ---
    pdf.add_page()
    pdf.set_left_margin(0.5)
    pdf.set_right_margin(0.5)
    _pdf_company_branding(pdf, pw, co)
    _pdf_summary_page(pdf, pw, sum_data)

    # Footer on last page
    pdf.ln(0.15)
    pdf.set_font('Helvetica', 'I', 7)
    pdf.cell(pw, 0.18, f"End of Report  |  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    pdf_bytes = pdf.output()
    output = BytesIO(pdf_bytes)
    name = co.get('event_name', '') or 'payroll'
    return StreamingResponse(output, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{name}_full_report.pdf"'})

# ---- CSV TEMPLATE DOWNLOAD ----
@api_router.get("/employees/template")
async def download_employee_template(request: Request):
    await get_current_user(request)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Dept/Emp Number", "Rate 1", "Rate 2", "Special Rate"])
    writer.writerow(["John Doe", "101", "25.00", "30.00", "15.00"])
    writer.writerow(["Jane Smith", "102", "28.50", "35.00", "20.00"])
    csv_bytes = output.getvalue().encode('utf-8')
    return StreamingResponse(BytesIO(csv_bytes), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="employee_import_template.csv"'})

# ---- ANALYTICS DASHBOARD ----
async def _build_analytics():
    """Aggregates totals across ALL events: KPIs, monthly trend, employer breakdown."""
    events = await db.events.find({}).to_list(2000)
    employees = await db.employees.find({}).to_list(20000)
    entries = await db.time_entries.find({}).to_list(50000)

    emp_by_id: dict = {str(e["_id"]): e for e in employees}
    event_by_id: dict = {str(ev["_id"]): ev for ev in events}

    totals = {"gross": 0.0, "benefit_co": 0.0, "fund_co": 0.0, "deduction": 0.0,
              "total_hours": 0.0, "events": len(events), "active_employees": 0}
    by_month: dict = {}     # 'YYYY-MM' -> dict of totals
    by_employer: dict = {}  # employer name -> dict of totals
    active_emp_set = set()

    for entry in entries:
        emp = emp_by_id.get(entry.get("employee_id"))
        ev = event_by_id.get(entry.get("event_id"))
        if not emp or not ev:
            continue
        r1 = float(emp.get("rate1", 0) or 0)
        r2 = float(emp.get("rate2", 0) or 0)
        spr = float(emp.get("special_rate", 0) or 0)
        gross = round(calc_gross_from_entry(r1, r2, spr, entry), 2)
        if gross == 0 and (
            (entry.get("st_r1", 0) + entry.get("ot_r1", 0) + entry.get("dt_r1", 0) +
             entry.get("st_r2", 0) + entry.get("ot_r2", 0) + entry.get("dt_r2", 0) +
             entry.get("sr_hours", 0)) == 0
        ):
            continue
        active_emp_set.add(entry.get("employee_id"))
        fp = float(ev.get("fund_pct", 0.02) or 0)
        bp = float(ev.get("benefit_pct", 0.21) or 0)
        dp = float(ev.get("deduction_pct", 0.05) or 0)
        hours = (entry.get("st_r1", 0) + entry.get("ot_r1", 0) + entry.get("dt_r1", 0) +
                 entry.get("st_r2", 0) + entry.get("ot_r2", 0) + entry.get("dt_r2", 0))
        benefit = round(bp * gross, 2)
        fund = round(fp * gross, 2)
        deduct = round(dp * gross, 2)

        totals["gross"] += gross
        totals["benefit_co"] += benefit
        totals["fund_co"] += fund
        totals["deduction"] += deduct
        totals["total_hours"] += hours

        # Month key from event created_at
        created = ev.get("created_at", "")
        month_key = (created[:7] if isinstance(created, str) and len(created) >= 7 else "unknown")
        bucket = by_month.setdefault(month_key, {"month": month_key, "gross": 0.0, "hours": 0.0, "benefit_co": 0.0, "fund_co": 0.0, "deduction": 0.0})
        bucket["gross"] += gross
        bucket["hours"] += hours
        bucket["benefit_co"] += benefit
        bucket["fund_co"] += fund
        bucket["deduction"] += deduct

        emp_label = (ev.get("employer", "") or "Unknown").strip() or "Unknown"
        ebucket = by_employer.setdefault(emp_label, {"employer": emp_label, "gross": 0.0, "hours": 0.0, "events": set()})
        ebucket["gross"] += gross
        ebucket["hours"] += hours
        ebucket["events"].add(entry.get("event_id"))

    totals["active_employees"] = len(active_emp_set)
    # Round totals
    for k in ("gross", "benefit_co", "fund_co", "deduction", "total_hours"):
        totals[k] = round(totals[k], 2)

    monthly = sorted(by_month.values(), key=lambda x: x["month"])
    for m in monthly:
        for k in ("gross", "hours", "benefit_co", "fund_co", "deduction"):
            m[k] = round(m[k], 2)

    employers = sorted(
        [{"employer": v["employer"], "gross": round(v["gross"], 2),
          "hours": round(v["hours"], 2), "event_count": len(v["events"])}
         for v in by_employer.values()],
        key=lambda x: x["gross"], reverse=True,
    )

    # Recent events list (lightweight, top 10)
    recent = sorted(events, key=lambda e: e.get("created_at", ""), reverse=True)[:10]
    recent_events = [{
        "id": str(e["_id"]),
        "event_name": e.get("event_name", ""),
        "employer": e.get("employer", ""),
        "job_number": e.get("job_number", ""),
        "created_at": e.get("created_at", ""),
    } for e in recent]

    return {"totals": totals, "monthly": monthly, "employers": employers, "recent_events": recent_events}

@api_router.get("/analytics/dashboard")
async def analytics_dashboard(request: Request):
    await get_current_user(request)
    return await _build_analytics()

# ---- USER GUIDE (one-page printable cheat sheet) ----
@api_router.get("/user-guide/pdf")
async def user_guide_pdf(request: Request):
    await get_current_user(request)
    pdf = FPDF(orientation='P', unit='in', format='Letter')
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.set_left_margin(0.5)
    pdf.set_right_margin(0.5)
    pdf.set_top_margin(0.4)
    pw = 8.5 - 1.0  # 7.5"

    # ---- Header ----
    pdf.set_font('Helvetica', 'B', 18)
    pdf.cell(pw, 0.3, "MEBO Payroll System", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(pw, 0.18, "User Guide  |  Quick Reference", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(0.1)

    # Two-column layout: each column 3.6" wide with 0.3" gutter
    col_w = 3.6
    gutter = 0.3
    left_x = 0.5
    right_x = 0.5 + col_w + gutter
    start_y = pdf.get_y()

    def section(x, y, title, items):
        pdf.set_xy(x, y)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_fill_color(240, 240, 245)
        pdf.cell(col_w, 0.22, f"  {title}", border=0, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Helvetica', '', 8.5)
        cur_y = pdf.get_y() + 0.04
        for label, desc in items:
            pdf.set_xy(x, cur_y)
            pdf.set_font('Helvetica', 'B', 8.5)
            pdf.cell(1.0, 0.16, label, new_x="RIGHT", new_y="TOP")
            pdf.set_font('Helvetica', '', 8.5)
            # Wrapped description in remaining width
            pdf.set_xy(x + 1.0, cur_y)
            pdf.multi_cell(col_w - 1.0, 0.16, desc, new_x="LMARGIN", new_y="NEXT")
            cur_y = pdf.get_y() + 0.02
        return cur_y + 0.12

    # ---- LEFT COLUMN ----
    y = start_y

    y = section(left_x, y, "ROLES", [
        ("Admin", "Full access + user management"),
        ("User", "Full payroll edit, no users"),
        ("Viewer", "Read-only + can export"),
    ])

    y = section(left_x, y, "EVENTS PAGE", [
        ("New Event", "Create event (name/job/employer/venue)"),
        ("Open", "Click any row in the list"),
        ("Clone", "Copy icon: duplicates employees+rates, blanks hours"),
        ("Delete", "Trash icon (confirms first)"),
        ("Dashboard", "Top-right nav for analytics"),
    ])

    y = section(left_x, y, "INFO TAB", [
        ("Pay Period", "Set start/end -> auto-fills Day 1-10 dates"),
        ("Branding", "Company name/email/phone shown on PDF/Excel"),
        ("Percentages", "Fund / Benefit / Deduction (saved per event)"),
        ("Notes", "Optional per-day notes"),
    ])

    y = section(left_x, y, "EMPLOYEES TAB", [
        ("Add", "+ button to add one at a time"),
        ("Edit", "Pencil -> change rates -> save/cancel"),
        ("Reorder", "Drag the grip handle"),
        ("Sort", "Click Name or Dept header to sort"),
        ("Search", "Filter by name or dept"),
        ("Template", "Download CSV template"),
        ("Import", "CSV / XLSX with per-row validation report"),
    ])

    # ---- RIGHT COLUMN ----
    y2 = start_y

    y2 = section(right_x, y2, "DAY 1-10 TABS", [
        ("Input mode", "Spreadsheet grid: ST/OT/DT (R1+R2) + SR"),
        ("Statement", "Toggle to read-only daily statement"),
        ("Fill column", "Click a column header (look for sparkle icon)"),
        ("Copy from", "Copy hours from any other day"),
        ("Tab / Enter", "Move between cells (Shift+Enter goes back)"),
        ("Save Day", "Commits all hour edits"),
        ("Print PDF", "Per-day statement PDF (8.5x11 letter)"),
    ])

    y2 = section(right_x, y2, "SUMMARY TAB", [
        ("Sum-Totals", "Read-only totals across all 10 days"),
        ("Excel", "Full styled summary workbook"),
        ("Summary PDF", "Landscape, branded, 5-col Grand Total"),
        ("Full Report", "Cover + every day + summary in one PDF"),
        ("Hidden zero", "Employees with no hours auto-hidden"),
    ])

    y2 = section(right_x, y2, "DASHBOARD", [
        ("KPIs", "Gross, Benefits, Fund, Deductions, Hours, etc."),
        ("Chart", "Monthly trend bar chart"),
        ("By Employer", "Sorted by gross"),
        ("Dashboard XLS", "Overview / Monthly / By Employer"),
        ("Employee Rpt", "Running totals per person, all events"),
    ])

    y2 = section(right_x, y2, "TIPS", [
        ("Auto-save", "Switching tabs saves Info/Day automatically"),
        ("Filter+Fill", "Search to filter, then column-fill applies only to filtered"),
        ("Clone weekly", "Use Clone Event for recurring pay periods"),
        ("Health check", "/api/health for uptime monitors"),
    ])

    # ---- Footer ----
    pdf.set_y(-0.5)
    pdf.set_font('Helvetica', 'I', 7.5)
    pdf.set_text_color(140, 140, 140)
    pdf.cell(pw, 0.18, f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  |  MEBO Payroll System  |  One-page Quick Reference", align='C')

    pdf_bytes = pdf.output()
    output = BytesIO(pdf_bytes)
    return StreamingResponse(
        output, media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="MEBO_user_guide.pdf"'},
    )

@api_router.get("/analytics/export/excel")
async def analytics_export_excel(request: Request):
    await get_current_user(request)
    data = await _build_analytics()
    wb = openpyxl.Workbook()
    hdr_font = Font(bold=True, size=11)
    hdr_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    money_fmt = '$#,##0.00'
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # --- Sheet 1: Overview ---
    ws = wb.active
    ws.title = "Overview"
    ws.append(["Metric", "Value"])
    for cell in ws[1]:
        cell.font = hdr_font; cell.fill = hdr_fill; cell.border = border
    rows = [
        ("Total Gross Payroll", data["totals"]["gross"], money_fmt),
        ("Total Benefits", data["totals"]["benefit_co"], money_fmt),
        ("Total Fund Contributions", data["totals"]["fund_co"], money_fmt),
        ("Total Deductions", data["totals"]["deduction"], money_fmt),
        ("Total Hours Worked", data["totals"]["total_hours"], '#,##0.00'),
        ("Active Employees (with hours)", data["totals"]["active_employees"], '0'),
        ("Total Events", data["totals"]["events"], '0'),
    ]
    for label, val, fmt in rows:
        ws.append([label, val])
        ws.cell(row=ws.max_row, column=2).number_format = fmt
        for cell in ws[ws.max_row]:
            cell.border = border
    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 22

    # --- Sheet 2: Monthly Trend ---
    ws2 = wb.create_sheet("Monthly")
    ws2.append(["Month", "Gross", "Benefits", "Fund", "Deductions", "Hours"])
    for cell in ws2[1]:
        cell.font = hdr_font; cell.fill = hdr_fill; cell.border = border
    for m in data["monthly"]:
        ws2.append([m["month"], m["gross"], m["benefit_co"], m["fund_co"], m["deduction"], m["hours"]])
        for c in [2, 3, 4, 5]:
            ws2.cell(row=ws2.max_row, column=c).number_format = money_fmt
        ws2.cell(row=ws2.max_row, column=6).number_format = '#,##0.00'
        for cell in ws2[ws2.max_row]:
            cell.border = border
    for col_letter, w in zip("ABCDEF", [14, 16, 16, 16, 16, 14]):
        ws2.column_dimensions[col_letter].width = w

    # --- Sheet 3: By Employer ---
    ws3 = wb.create_sheet("By Employer")
    ws3.append(["Employer", "Events", "Hours", "Gross"])
    for cell in ws3[1]:
        cell.font = hdr_font; cell.fill = hdr_fill; cell.border = border
    for e in data["employers"]:
        ws3.append([e["employer"], e["event_count"], e["hours"], e["gross"]])
        ws3.cell(row=ws3.max_row, column=3).number_format = '#,##0.00'
        ws3.cell(row=ws3.max_row, column=4).number_format = money_fmt
        for cell in ws3[ws3.max_row]:
            cell.border = border
    for col_letter, w in zip("ABCD", [28, 10, 14, 18]):
        ws3.column_dimensions[col_letter].width = w

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="payroll_analytics.xlsx"'},
    )

@api_router.get("/analytics/employee-report/excel")
async def analytics_employee_report_excel(request: Request):
    """Per-employee aggregated report across ALL events. Excel only."""
    await get_current_user(request)
    events = await db.events.find({}).to_list(2000)
    employees = await db.employees.find({}).to_list(20000)
    entries = await db.time_entries.find({}).to_list(50000)

    emp_by_id: dict = {str(e["_id"]): e for e in employees}
    event_by_id: dict = {str(ev["_id"]): ev for ev in events}

    # Group by name across events (running total per employee). Different
    # dept numbers across events are joined into a comma-separated list.
    agg: dict = {}

    def _norm_name(s: str) -> str:
        # Collapse whitespace & lowercase for matching, so "John Doe" and "John  Doe" merge.
        return " ".join((s or "").split()).lower()

    def _merge_dept(existing: str, new: str) -> str:
        new = (new or "").strip()
        if not new:
            return existing
        existing_parts = [p.strip() for p in (existing or "").split(",") if p.strip()]
        if new in existing_parts:
            return existing
        existing_parts.append(new)
        return ", ".join(existing_parts)

    # Pre-populate buckets for ALL employees so people with zero hours still appear
    for emp in employees:
        name = (emp.get("name", "") or "").strip()
        dept = (emp.get("dept_emp_num", "") or "").strip()
        if not name:
            continue
        key = _norm_name(name)
        bucket = agg.setdefault(key, {
            "name": name, "dept_emp_num": "",
            "hours": 0.0, "sr_hours": 0.0, "gross": 0.0, "benefit_co": 0.0,
            "fund_co": 0.0, "deduction": 0.0, "events": set(), "rows": [],
        })
        bucket["dept_emp_num"] = _merge_dept(bucket["dept_emp_num"], dept)

    for entry in entries:
        emp = emp_by_id.get(entry.get("employee_id"))
        ev = event_by_id.get(entry.get("event_id"))
        if not emp or not ev:
            continue
        hours = (entry.get("st_r1", 0) + entry.get("ot_r1", 0) + entry.get("dt_r1", 0) +
                 entry.get("st_r2", 0) + entry.get("ot_r2", 0) + entry.get("dt_r2", 0))
        sr_hours = entry.get("sr_hours", 0)
        if hours == 0 and sr_hours == 0:
            continue
        r1 = float(emp.get("rate1", 0) or 0)
        r2 = float(emp.get("rate2", 0) or 0)
        spr = float(emp.get("special_rate", 0) or 0)
        gross = round(calc_gross_from_entry(r1, r2, spr, entry), 2)
        bp = float(ev.get("benefit_pct", 0.21) or 0)
        fp = float(ev.get("fund_pct", 0.02) or 0)
        dp = float(ev.get("deduction_pct", 0.05) or 0)
        benefit = round(bp * gross, 2)
        fund = round(fp * gross, 2)
        deduct = round(dp * gross, 2)

        name = (emp.get("name", "") or "").strip()
        dept = (emp.get("dept_emp_num", "") or "").strip()
        if not name:
            continue
        key = _norm_name(name)
        bucket = agg.setdefault(key, {
            "name": name, "dept_emp_num": "",
            "hours": 0.0, "sr_hours": 0.0, "gross": 0.0, "benefit_co": 0.0,
            "fund_co": 0.0, "deduction": 0.0, "events": set(), "rows": [],
        })
        bucket["dept_emp_num"] = _merge_dept(bucket["dept_emp_num"], dept)
        bucket["hours"] += hours
        bucket["sr_hours"] += sr_hours
        bucket["gross"] += gross
        bucket["benefit_co"] += benefit
        bucket["fund_co"] += fund
        bucket["deduction"] += deduct
        bucket["events"].add(entry.get("event_id"))
        bucket["rows"].append({
            "event_name": ev.get("event_name", ""),
            "employer": ev.get("employer", ""),
            "job_number": ev.get("job_number", ""),
            "day": entry.get("day_number", ""),
            "hours": hours, "sr_hours": sr_hours,
            "gross": gross, "benefit": benefit, "fund": fund, "deduct": deduct,
        })

    # Sort: employees with hours first (by gross desc), then zero-hour employees alphabetically
    rows = sorted(agg.values(), key=lambda x: (-x["gross"], x["name"].lower()))

    # Build workbook
    wb = openpyxl.Workbook()
    hdr_font = Font(bold=True, size=11)
    hdr_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    total_fill = PatternFill(start_color="E8EAF0", end_color="E8EAF0", fill_type="solid")
    money_fmt = '$#,##0.00'
    hours_fmt = '#,##0.00'
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # --- Sheet 1: Per-Employee Summary ---
    ws = wb.active
    ws.title = "Employee Summary"
    headers = ["Employee", "Dept/Emp #", "Events", "Total Hours", "SR Hours",
               "Gross", "Benefits", "Fund", "Deductions", "Net (Gross - Deductions)"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = hdr_font; cell.fill = hdr_fill; cell.border = border
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    for r in rows:
        net = round(r["gross"] - r["deduction"], 2)
        ws.append([r["name"], r["dept_emp_num"], len(r["events"]),
                   round(r["hours"], 2), round(r["sr_hours"], 2),
                   round(r["gross"], 2), round(r["benefit_co"], 2),
                   round(r["fund_co"], 2), round(r["deduction"], 2), net])
        for c in [4, 5]:
            ws.cell(row=ws.max_row, column=c).number_format = hours_fmt
        for c in [6, 7, 8, 9, 10]:
            ws.cell(row=ws.max_row, column=c).number_format = money_fmt
        for cell in ws[ws.max_row]:
            cell.border = border
            if cell.column > 2:
                cell.alignment = Alignment(horizontal='right')
    # Totals row
    if rows:
        t_hours = sum(r["hours"] for r in rows)
        t_sr = sum(r["sr_hours"] for r in rows)
        t_gross = sum(r["gross"] for r in rows)
        t_benefit = sum(r["benefit_co"] for r in rows)
        t_fund = sum(r["fund_co"] for r in rows)
        t_deduct = sum(r["deduction"] for r in rows)
        ws.append(["TOTALS", "", "", round(t_hours, 2), round(t_sr, 2),
                   round(t_gross, 2), round(t_benefit, 2), round(t_fund, 2),
                   round(t_deduct, 2), round(t_gross - t_deduct, 2)])
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True); cell.fill = total_fill; cell.border = border
        for c in [4, 5]:
            ws.cell(row=ws.max_row, column=c).number_format = hours_fmt
        for c in [6, 7, 8, 9, 10]:
            ws.cell(row=ws.max_row, column=c).number_format = money_fmt
    for col_letter, w in zip("ABCDEFGHIJ", [26, 14, 9, 12, 11, 14, 14, 12, 14, 22]):
        ws.column_dimensions[col_letter].width = w

    # --- Sheet 2: Per-Employee Per-Event Detail ---
    ws2 = wb.create_sheet("Detail by Event")
    headers2 = ["Employee", "Dept/Emp #", "Event", "Employer", "Job #", "Day",
                "Hours", "SR Hours", "Gross", "Benefits", "Fund", "Deductions"]
    ws2.append(headers2)
    for cell in ws2[1]:
        cell.font = hdr_font; cell.fill = hdr_fill; cell.border = border
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    for r in rows:
        for sub in r["rows"]:
            ws2.append([r["name"], r["dept_emp_num"], sub["event_name"], sub["employer"],
                        sub["job_number"], sub["day"], sub["hours"], sub["sr_hours"],
                        sub["gross"], sub["benefit"], sub["fund"], sub["deduct"]])
            for c in [7, 8]:
                ws2.cell(row=ws2.max_row, column=c).number_format = hours_fmt
            for c in [9, 10, 11, 12]:
                ws2.cell(row=ws2.max_row, column=c).number_format = money_fmt
            for cell in ws2[ws2.max_row]:
                cell.border = border
    for col_letter, w in zip("ABCDEFGHIJKL", [24, 14, 22, 18, 10, 6, 10, 10, 14, 14, 12, 14]):
        ws2.column_dimensions[col_letter].width = w

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="employee_report.xlsx"'},
    )

# ---- SUM TOTALS ----
async def _get_sum_totals_data(event_id: str):
    event = await db.events.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    employees = await db.employees.find({"event_id": event_id}).sort("sort_order", 1).to_list(200)
    all_entries = await db.time_entries.find({"event_id": event_id}).to_list(2000)
    fp, bp, dp = event.get("fund_pct", 0.02), event.get("benefit_pct", 0.21), event.get("deduction_pct", 0.05)
    entry_map = {}
    for e in all_entries:
        entry_map.setdefault(e["employee_id"], []).append(e)
    result = []
    for emp in employees:
        eid = str(emp["_id"])
        ents = entry_map.get(eid, [])
        ts1 = sum(e.get("st_r1", 0) for e in ents)
        to1 = sum(e.get("ot_r1", 0) for e in ents)
        td1 = sum(e.get("dt_r1", 0) for e in ents)
        ts2 = sum(e.get("st_r2", 0) for e in ents)
        to2 = sum(e.get("ot_r2", 0) for e in ents)
        td2 = sum(e.get("dt_r2", 0) for e in ents)
        tsr = sum(e.get("sr_hours", 0) for e in ents)
        r1, r2, spr = emp.get("rate1", 0), emp.get("rate2", 0), emp.get("special_rate", 0)
        tgross = sum(calc_gross_from_entry(r1, r2, spr, e) for e in ents)
        tgross = round(tgross, 2)
        result.append({
            "employee_id": eid, "name": emp.get("name",""), "dept_emp_num": emp.get("dept_emp_num",""),
            "rate1": r1, "rate2": r2, "special_rate": spr,
            "r1_st": ts1, "r1_ot": to1, "r1_dt": td1,
            "r2_st": ts2, "r2_ot": to2, "r2_dt": td2,
            "sr_hours": tsr, "special_tot": round(spr * tsr, 2),
            "total_hours": ts1+to1+td1+ts2+to2+td2, "gross": tgross,
            "benefit_co": round(bp * tgross, 2), "fund_co": round(fp * tgross, 2), "deduction": round(dp * tgross, 2),
        })
    return {
        "event": {"event_name": event.get("event_name",""), "employer": event.get("employer",""),
                  "venue": event.get("venue",""), "job_number": event.get("job_number",""),
                  "payroll_name": event.get("payroll_name",""), "days": event.get("days", {}),
                  "company_name": event.get("company_name",""), "company_email": event.get("company_email",""),
                  "company_phone": event.get("company_phone",""),
                  "pay_period_start": event.get("pay_period_start",""), "pay_period_end": event.get("pay_period_end","")},
        "fund_pct": fp, "benefit_pct": bp, "deduction_pct": dp, "employees": result,
    }

@api_router.get("/events/{event_id}/sum-totals")
async def get_sum_totals(event_id: str, request: Request):
    await get_current_user(request)
    return await _get_sum_totals_data(event_id)

# ---- EXPORT EXCEL ----
@api_router.get("/events/{event_id}/export/excel")
async def export_excel(event_id: str, request: Request):
    await get_current_user(request)
    data = await _get_sum_totals_data(event_id)
    # Hide employees with no hours entered yet from the Excel export
    data = {**data, "employees": [e for e in data["employees"] if (e.get("total_hours") or 0) > 0]}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sum-Totals"
    hdr_font = Font(bold=True, size=10)
    hdr_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    r2_hdr_fill = PatternFill(start_color="FFE0B2", end_color="FFE0B2", fill_type="solid")
    r2_cell_fill = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid")
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    r2_cols = {7, 8, 9, 10}  # 1-indexed: Rate 2, R2 ST, R2 OT, R2 DT
    # Event info
    ws.append([f"Event: {data['event']['event_name']}", "", f"Employer: {data['event']['employer']}", "",
               f"Job #: {data['event']['job_number']}", "", f"Venue: {data['event']['venue']}"])
    ws.append([])
    headers = ["Employee", "Dept/Emp #", "Rate 1", "R1 ST", "R1 OT", "R1 DT", "Rate 2", "R2 ST", "R2 OT", "R2 DT",
               "SR Rate", "SR Hrs", "SR Total", "Total Hrs", f"Benefit ({data['benefit_pct']*100:.0f}%)",
               f"Fund ({data['fund_pct']*100:.0f}%)", f"Deduct ({data['deduction_pct']*100:.0f}%)", "Gross Total"]
    ws.append(headers)
    for cell in ws[ws.max_row]:
        cell.font = hdr_font
        cell.fill = r2_hdr_fill if cell.column in r2_cols else hdr_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    for emp in data["employees"]:
        row = [emp["name"], emp["dept_emp_num"], emp["rate1"], emp["r1_st"], emp["r1_ot"], emp["r1_dt"],
               emp["rate2"], emp["r2_st"], emp["r2_ot"], emp["r2_dt"], emp["special_rate"],
               emp["sr_hours"], emp["special_tot"], emp["total_hours"],
               emp["benefit_co"], emp["fund_co"], emp["deduction"], emp["gross"]]
        ws.append(row)
        for cell in ws[ws.max_row]:
            cell.border = border
            if cell.column in r2_cols:
                cell.fill = r2_cell_fill
            if cell.column > 2:
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal='right')
    # Totals row
    totals = ["TOTALS", ""] + [sum(emp[k] for emp in data["employees"]) for k in
              ["rate1", "r1_st", "r1_ot", "r1_dt", "rate2", "r2_st", "r2_ot", "r2_dt",
               "special_rate", "sr_hours", "special_tot", "total_hours", "benefit_co", "fund_co", "deduction", "gross"]]
    totals[2] = ""  # rate1 total doesn't make sense
    totals[6] = ""  # rate2 total
    totals[10] = ""  # sr rate total
    ws.append(totals)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
        cell.border = border
        if cell.column in r2_cols:
            cell.fill = r2_cell_fill
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, 8), 18)

    # Grand Total summary section
    emps = data["employees"]
    t_gross = sum(e["gross"] for e in emps)
    t_benefit = sum(e["benefit_co"] for e in emps)
    t_fund = sum(e["fund_co"] for e in emps)
    t_deduct = sum(e["deduction"] for e in emps)
    gt = t_gross + t_benefit + t_fund + t_deduct

    ws.append([])
    gt_fill = PatternFill(start_color="E8EAF0", end_color="E8EAF0", fill_type="solid")
    gt_bold = Font(bold=True, size=11)
    gt_label_font = Font(size=10)
    gt_total_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    # Header
    r = ws.max_row + 1
    ws.cell(row=r, column=16, value="GRAND TOTAL").font = gt_bold
    ws.cell(row=r, column=16).fill = gt_fill
    ws.cell(row=r, column=16).border = border
    ws.cell(row=r, column=16).alignment = Alignment(horizontal='center')
    ws.merge_cells(start_row=r, start_column=16, end_row=r, end_column=18)
    for c in [17, 18]:
        ws.cell(row=r, column=c).border = border
        ws.cell(row=r, column=c).fill = gt_fill

    for label, val in [("Gross Salary", t_gross), ("Benefits", t_benefit), ("Fund", t_fund), ("Deductions", t_deduct)]:
        r += 1
        ws.cell(row=r, column=16, value=label).font = gt_label_font
        ws.cell(row=r, column=16).border = border
        ws.merge_cells(start_row=r, start_column=16, end_row=r, end_column=17)
        ws.cell(row=r, column=17).border = border
        ws.cell(row=r, column=18, value=val).font = gt_label_font
        ws.cell(row=r, column=18).number_format = '$#,##0.00'
        ws.cell(row=r, column=18).alignment = Alignment(horizontal='right')
        ws.cell(row=r, column=18).border = border

    r += 1
    ws.cell(row=r, column=16, value="Grand Total").font = gt_bold
    ws.cell(row=r, column=16).fill = gt_total_fill
    ws.cell(row=r, column=16).border = border
    ws.merge_cells(start_row=r, start_column=16, end_row=r, end_column=17)
    ws.cell(row=r, column=17).border = border
    ws.cell(row=r, column=17).fill = gt_total_fill
    ws.cell(row=r, column=18, value=gt).font = gt_bold
    ws.cell(row=r, column=18).number_format = '$#,##0.00'
    ws.cell(row=r, column=18).alignment = Alignment(horizontal='right')
    ws.cell(row=r, column=18).fill = gt_total_fill
    ws.cell(row=r, column=18).border = border

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    name = data['event']['event_name'] or 'payroll'
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}_summary.xlsx"'})

# ---- EXPORT PDF (8.5 x 11 Letter) ----
@api_router.get("/events/{event_id}/export/pdf")
async def export_pdf(event_id: str, request: Request):
    await get_current_user(request)
    data = await _get_sum_totals_data(event_id)
    # Hide employees with no hours entered yet from the summary PDF
    data = {**data, "employees": [e for e in data["employees"] if (e.get("total_hours") or 0) > 0]}
    # 8.5 x 11 inch = Letter size, landscape for wide tables
    pdf = FPDF(orientation='L', unit='in', format='Letter')
    pdf.set_auto_page_break(auto=True, margin=0.5)
    pdf.add_page()
    pw = 11 - 1.0  # usable width = 10 inches (0.5in margins each side)
    pdf.set_left_margin(0.5)
    pdf.set_right_margin(0.5)

    # Company branding - left header
    co = data['event']
    if co.get('company_name'):
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(pw, 0.3, co['company_name'], new_x="LMARGIN", new_y="NEXT")
        brand_line = []
        if co.get('company_email'):
            brand_line.append(co['company_email'])
        if co.get('company_phone'):
            brand_line.append(co['company_phone'])
        if brand_line:
            pdf.set_font('Helvetica', '', 8)
            pdf.cell(pw, 0.2, "  |  ".join(brand_line), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.1)

    # Header
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(pw, 0.35, "Payroll Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 11)
    pdf.cell(pw, 0.25, f"{data['event']['event_name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(pw/3, 0.22, f"Employer: {data['event']['employer']}")
    pdf.cell(pw/3, 0.22, f"Venue: {data['event']['venue']}")
    pdf.cell(pw/3, 0.22, f"Job #: {data['event']['job_number']}", new_x="LMARGIN", new_y="NEXT")
    if data['event'].get('payroll_name'):
        pdf.cell(pw, 0.22, f"Prepared by: {data['event']['payroll_name']}", new_x="LMARGIN", new_y="NEXT")

    # Rate info line
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(pw, 0.2, f"Fund: {data['fund_pct']*100:.1f}%  |  Benefit: {data['benefit_pct']*100:.1f}%  |  Deduction: {data['deduction_pct']*100:.1f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.1)

    # Table headers
    headers = ["#", "Employee", "Dept#", "Rate 1", "R1 ST", "R1 OT", "R1 DT", "Rate 2",
               "R2 ST", "R2 OT", "R2 DT", "SR Rate", "SR Hrs", "SR Tot", "Tot Hrs",
               "Benefit", "Fund", "Deduct", "Gross Total"]
    widths = [0.3, 1.2, 0.65, 0.5, 0.45, 0.45, 0.45, 0.5,
              0.45, 0.45, 0.45, 0.5, 0.42, 0.52, 0.48,
              0.58, 0.5, 0.5, 0.73]
    rh = 0.22  # row height

    r2_pdf_cols = {7, 8, 9, 10}  # Rate 2, R2 ST, R2 OT, R2 DT

    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_draw_color(180, 180, 180)
    for i, h in enumerate(headers):
        if i in r2_pdf_cols:
            pdf.set_fill_color(255, 224, 178)
        else:
            pdf.set_fill_color(230, 235, 245)
        pdf.cell(widths[i], rh, h, border=1, fill=True, align='C')
    pdf.ln()

    # Data rows
    pdf.set_font('Helvetica', '', 7)
    for idx, emp in enumerate(data["employees"]):
        if pdf.get_y() > 7.5:  # near bottom of 8.5in page in landscape
            pdf.add_page()
            pdf.set_font('Helvetica', 'B', 7)
            for i, h in enumerate(headers):
                if i in r2_pdf_cols:
                    pdf.set_fill_color(255, 224, 178)
                else:
                    pdf.set_fill_color(230, 235, 245)
                pdf.cell(widths[i], rh, h, border=1, fill=True, align='C')
            pdf.ln()
            pdf.set_font('Helvetica', '', 7)

        vals = [str(idx+1), emp["name"][:18], emp["dept_emp_num"][:10],
                f"${emp['rate1']:.2f}", f"{emp['r1_st']:.1f}", f"{emp['r1_ot']:.1f}", f"{emp['r1_dt']:.1f}",
                f"${emp['rate2']:.2f}", f"{emp['r2_st']:.1f}", f"{emp['r2_ot']:.1f}", f"{emp['r2_dt']:.1f}",
                f"${emp['special_rate']:.2f}", f"{emp['sr_hours']:.1f}", f"${emp['special_tot']:.2f}",
                f"{emp['total_hours']:.1f}", f"${emp['benefit_co']:.2f}", f"${emp['fund_co']:.2f}",
                f"${emp['deduction']:.2f}", f"${emp['gross']:.2f}"]
        for i, v in enumerate(vals):
            align = 'L' if i <= 2 else 'R'
            if i in r2_pdf_cols:
                pdf.set_fill_color(255, 243, 224)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            elif idx % 2 == 1:
                pdf.set_fill_color(245, 247, 250)
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=True)
            else:
                pdf.cell(widths[i], rh, v, border=1, align=align, fill=False)
        pdf.ln()

    # Totals row
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(220, 225, 240)
    emps = data["employees"]
    t_gross = sum(e['gross'] for e in emps)
    t_benefit = sum(e['benefit_co'] for e in emps)
    t_fund = sum(e['fund_co'] for e in emps)
    t_deduct = sum(e['deduction'] for e in emps)
    tot_vals = ["", "TOTALS", "",
                "", f"{sum(e['r1_st'] for e in emps):.1f}", f"{sum(e['r1_ot'] for e in emps):.1f}",
                f"{sum(e['r1_dt'] for e in emps):.1f}", "",
                f"{sum(e['r2_st'] for e in emps):.1f}", f"{sum(e['r2_ot'] for e in emps):.1f}",
                f"{sum(e['r2_dt'] for e in emps):.1f}", "",
                f"{sum(e['sr_hours'] for e in emps):.1f}", f"${sum(e['special_tot'] for e in emps):.2f}",
                f"{sum(e['total_hours'] for e in emps):.1f}", f"${t_benefit:.2f}",
                f"${t_fund:.2f}", f"${t_deduct:.2f}", f"${t_gross:.2f}"]
    for i, v in enumerate(tot_vals):
        align = 'L' if i <= 2 else 'R'
        if i in r2_pdf_cols:
            pdf.set_fill_color(255, 236, 200)
        else:
            pdf.set_fill_color(220, 225, 240)
        pdf.cell(widths[i], rh + 0.03, v, border=1, align=align, fill=True)
    pdf.ln()

    # Grand Total box
    _pdf_grand_total_box(pdf, pw, t_gross, t_benefit, t_fund, t_deduct)

    # Footer
    pdf.ln(0.15)
    pdf.set_font('Helvetica', 'I', 7)
    pdf.cell(pw, 0.18, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  |  Page {{nb}}")

    pdf_bytes = pdf.output()
    output = BytesIO(pdf_bytes)
    name = data['event']['event_name'] or 'payroll'
    return StreamingResponse(output, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{name}_summary.pdf"'})

# ---- STARTUP ----
async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "email": admin_email, "password_hash": hash_password(admin_password),
            "name": "Admin", "role": "admin", "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Admin user created: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        logger.info("Admin password updated")

@app.on_event("startup")
async def startup():
    # Index creation is best-effort: some managed Mongo providers restrict
    # createIndexes permissions for app users. Don't let that crash boot.
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index([("created_at", -1)])
        await db.events.create_index([("created_at", -1)])
        await db.events.create_index("job_number")
        await db.time_entries.create_index([("event_id", 1), ("employee_id", 1), ("day_number", 1)], unique=True)
        await db.time_entries.create_index([("event_id", 1), ("day_number", 1)])
        logger.info("Indexes ensured")
    except Exception as e:
        logger.warning(f"Index creation skipped ({type(e).__name__}): {e}")
    try:
        await seed_admin()
    except Exception as e:
        logger.error(f"seed_admin failed ({type(e).__name__}): {e}")
    logger.info("Server started")

@app.on_event("shutdown")
async def shutdown():
    client.close()

app.include_router(api_router)

_allowed_origins_raw = os.environ.get("FRONTEND_URL", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
