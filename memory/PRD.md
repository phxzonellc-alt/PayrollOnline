# MEBO Online Payroll System - PRD

## Original Problem Statement
Build an online payroll system that uses the attached .xlsm file for the variables and format. Event-based payroll with admin login, up to 200 employees, 10 work days, dual rate system, PDF/Excel export.

## Architecture
- **Backend**: FastAPI + MongoDB (Motor async driver)
- **Frontend**: React + Shadcn UI + Tailwind CSS
- **Auth**: JWT httpOnly cookies
- **Export**: openpyxl (Excel), fpdf2 (PDF)

## User Personas
- **Payroll Admin**: Creates events, manages employees, enters daily hours, reviews statements, exports reports

## Core Requirements
- Admin JWT authentication
- Event CRUD (job #, employer, venue, dates, notes, fund/benefit/deduction %)
- Employee management (name, dept, rate1, rate2, special rate) - up to 200 per event
- Daily time entry (ST/OT/DT for Rate 1 & Rate 2 + Special Rate hours) for 10 days
- Auto-calculated: Gross Total, Fund CO, Benefit CO, Deduction (matching Excel formulas)
- Daily statements (D1-D10) and Sum-Totals summary
- PDF and Excel export

## What's Implemented (2026-04-13)
- Full admin auth (login/logout/me/refresh with JWT cookies)
- Events CRUD with all metadata fields
- Employee management per event
- Daily time entry with batch save
- Real-time client-side payroll calculations matching Excel formula
- Daily statements endpoint
- Sum-Totals aggregation
- Excel export (styled workbook)
- PDF export (landscape table)
- Swiss/high-contrast design with Cabinet Grotesk + IBM Plex Sans + JetBrains Mono

## Calculation Formula (from Excel)
```
IF R1_hours == 0:
  Gross = Rate2 * ST_R2 + Rate2 * 1.5 * OT_R2 + Rate2 * 2 * DT_R2 + SpecialRate * SR
ELSE:
  Gross = Rate1 * ST_R1 + Rate1 * 1.5 * OT_R1 + Rate1 * 2 * DT_R1 + SpecialRate * SR

Fund CO = Fund% * Gross (default 2%)
Benefit CO = Benefit% * Gross (default 21%)
Deduction = Deduction% * Gross (default 5%)
```

## Prioritized Backlog
### P0 - Complete
- [x] Auth, Events, Employees, Time Entry, Calculations, Export
- [x] Inline employee editing (pencil icon -> edit fields -> save/cancel)
- [x] Bulk employee import from CSV/Excel
- [x] PDF export formatted for 8.5 x 11 Letter landscape
- [x] Read-only daily statements (Input/Statement toggle on each Day tab)
- [x] Daily statement PDF print (per-day 8.5x11 Letter PDF)
- [x] CSV template download for employee import

### P1 - Next
- [ ] Employee sorting/reordering via drag-and-drop

### P2 - Future
- [ ] Multi-user support with role-based access
- [ ] Email payslips to employees
- [ ] Payroll history and audit trail
- [ ] Dashboard with charts (total spend, hours breakdown)
