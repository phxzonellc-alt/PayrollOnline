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
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from fpdf import FPDF

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

# ---- EVENTS CRUD ----
@api_router.post("/events")
async def create_event(request: Request):
    await get_current_user(request)
    body = await request.json()
    event = {
        "job_number": body.get("job_number", ""),
        "event_name": body.get("event_name", ""),
        "employer": body.get("employer", ""),
        "venue": body.get("venue", ""),
        "payroll_name": body.get("payroll_name", ""),
        "contact_email": body.get("contact_email", ""),
        "cell_phone": body.get("cell_phone", ""),
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
    await get_current_user(request)
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
    await get_current_user(request)
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
    await get_current_user(request)
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
    await get_current_user(request)
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
    await get_current_user(request)
    await db.employees.delete_one({"_id": ObjectId(emp_id), "event_id": event_id})
    await db.time_entries.delete_many({"event_id": event_id, "employee_id": emp_id})
    return {"message": "Employee deleted"}

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
    await get_current_user(request)
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
def calc_gross(rate1, rate2, special_rate, st_r1, ot_r1, dt_r1, st_r2, ot_r2, dt_r2, sr_hours):
    if (st_r1 + ot_r1 + dt_r1) == 0:
        return (rate2 * st_r2) + (rate2 * 1.5 * ot_r2) + (rate2 * 2 * dt_r2) + (special_rate * sr_hours)
    return (rate1 * st_r1) + (rate1 * 1.5 * ot_r1) + (rate1 * 2 * dt_r1) + (special_rate * sr_hours)

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
        })
    return {"day": day, "fund_pct": fp, "benefit_pct": bp, "deduction_pct": dp, "employees": result}

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
        tgross = sum(calc_gross(r1, r2, spr, e.get("st_r1",0), e.get("ot_r1",0), e.get("dt_r1",0), e.get("st_r2",0), e.get("ot_r2",0), e.get("dt_r2",0), e.get("sr_hours",0)) for e in ents)
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
                  "payroll_name": event.get("payroll_name",""), "days": event.get("days", {})},
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
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
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
        cell.fill = hdr_fill
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
            if cell.column > 2:
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal='right')
    # Totals row
    last = ws.max_row
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
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, 8), 18)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    name = data['event']['event_name'] or 'payroll'
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}_summary.xlsx"'})

# ---- EXPORT PDF ----
@api_router.get("/events/{event_id}/export/pdf")
async def export_pdf(event_id: str, request: Request):
    await get_current_user(request)
    data = await _get_sum_totals_data(event_id)
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 8, f"Payroll Summary - {data['event']['event_name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 5, f"Employer: {data['event']['employer']}  |  Venue: {data['event']['venue']}  |  Job #: {data['event']['job_number']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    headers = ["Employee", "Dept#", "R1", "R1 ST", "R1 OT", "R1 DT", "R2", "R2 ST", "R2 OT", "R2 DT",
               "SR$", "SR Hr", "SR Tot", "Hrs", "Benefit", "Fund", "Deduct", "Gross"]
    widths = [38, 20, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 16, 14, 18, 16, 16, 20]
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(217, 225, 242)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 6, h, border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_font('Helvetica', '', 6.5)
    for emp in data["employees"]:
        vals = [emp["name"][:20], emp["dept_emp_num"][:12],
                f"{emp['rate1']:.2f}", f"{emp['r1_st']:.1f}", f"{emp['r1_ot']:.1f}", f"{emp['r1_dt']:.1f}",
                f"{emp['rate2']:.2f}", f"{emp['r2_st']:.1f}", f"{emp['r2_ot']:.1f}", f"{emp['r2_dt']:.1f}",
                f"{emp['special_rate']:.2f}", f"{emp['sr_hours']:.1f}", f"{emp['special_tot']:.2f}",
                f"{emp['total_hours']:.1f}", f"{emp['benefit_co']:.2f}", f"{emp['fund_co']:.2f}",
                f"{emp['deduction']:.2f}", f"{emp['gross']:.2f}"]
        for i, v in enumerate(vals):
            align = 'L' if i < 2 else 'R'
            pdf.cell(widths[i], 5, v, border=1, align=align)
        pdf.ln()
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
