from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
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
db = client[os.environ['DB_NAME']]

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
@api_router.post("/auth/login")
async def login(request: Request, response: Response):
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
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
    try:
        return float(val) if val else 0
    except (ValueError, TypeError):
        return 0

def _parse_emp_row(row, cols, event_id, sort_order):
    name_val = row[cols["name"]] if len(row) > cols["name"] else None
    if not name_val or not str(name_val).strip():
        return None
    return {
        "event_id": event_id,
        "name": str(name_val).strip(),
        "dept_emp_num": str(row[cols["dept"]]).strip() if len(row) > cols["dept"] and row[cols["dept"]] else "",
        "rate1": _safe_float(row[cols["r1"]] if len(row) > cols["r1"] else 0),
        "rate2": _safe_float(row[cols["r2"]] if len(row) > cols["r2"] else 0),
        "special_rate": _safe_float(row[cols["sr"]] if len(row) > cols["sr"] else 0),
        "sort_order": sort_order,
    }

# ---- BULK EMPLOYEE IMPORT ----
@api_router.post("/events/{event_id}/employees/import")
async def import_employees(event_id: str, request: Request, file: UploadFile = File(...)):
    await require_editor(request)
    content = await file.read()
    filename = file.filename or ""
    imported = []
    count = await db.employees.count_documents({"event_id": event_id})

    if filename.endswith(('.xlsx', '.xls')):
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        header = [str(c).strip().lower() if c else "" for c in rows[0]] if rows else []
        cols = _detect_columns(header)
        for row in rows[1:]:
            count += 1
            emp = _parse_emp_row(list(row), cols, event_id, count)
            if not emp:
                continue
            result = await db.employees.insert_one(emp)
            emp["id"] = str(result.inserted_id)
            emp.pop("_id", None)
            imported.append(emp)
    else:
        text = content.decode('utf-8-sig')
        reader = csv.reader(StringIO(text))
        header = [c.strip().lower() for c in next(reader, [])]
        cols = _detect_columns(header)
        for row in reader:
            count += 1
            emp = _parse_emp_row(row, cols, event_id, count)
            if not emp:
                continue
            result = await db.employees.insert_one(emp)
            emp["id"] = str(result.inserted_id)
            emp.pop("_id", None)
            imported.append(emp)

    return {"imported": len(imported), "employees": imported}

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
            "company_phone": event.get("company_phone", "")}

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

# ---- GRAND TOTAL BOX HELPER ----
def _pdf_grand_total_box(pdf, pw, t_gross, t_benefit, t_fund, t_deduct):
    gt = t_gross + t_benefit + t_fund + t_deduct
    pdf.ln(0.15)
    bw = 3.0
    pdf.set_draw_color(180, 180, 180)

    # Header
    pdf.set_fill_color(240, 242, 248)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(bw, 0.28, "GRAND TOTAL", border=1, fill=True, align='C')
    pdf.ln()

    # Line items
    pdf.set_font('Helvetica', '', 8)
    for label, val in [("Gross Salary", t_gross), ("Benefits", t_benefit), ("Fund", t_fund), ("Deductions", t_deduct)]:
        pdf.cell(bw * 0.6, 0.22, f"  {label}", border='LB')
        pdf.cell(bw * 0.4, 0.22, f"${val:,.2f}  ", border='RB', align='R')
        pdf.ln()

    # Grand Total row
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(220, 225, 240)
    pdf.cell(bw * 0.6, 0.28, "  Grand Total", border=1, fill=True)
    pdf.cell(bw * 0.4, 0.28, f"${gt:,.2f}  ", border=1, fill=True, align='R')
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
                  "company_phone": event.get("company_phone","")},
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
    await db.users.create_index("email", unique=True)
    await db.time_entries.create_index([("event_id", 1), ("employee_id", 1), ("day_number", 1)], unique=True)
    await seed_admin()
    logger.info("Server started, admin seeded")

@app.on_event("shutdown")
async def shutdown():
    client.close()

app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
