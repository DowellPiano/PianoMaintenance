# Piano Maintainer — CMMS for Pianos

A Computerized Maintenance Management System (CMMS) built for piano technicians and facilities managers. Modeled after [Limble CMMS](https://limblecmms.com), Piano Maintainer handles preventive maintenance scheduling, work order management, technician dispatch, and parts tracking — purpose-built for piano fleets in schools, venues, and studios.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3 · Django 5.2 · Django REST Framework |
| Frontend | React 18 · Vite · React Router |
| Database | SQLite (dev) |
| Auth | Django session auth (custom `Technician` user model) |

---

## How It Works

### Core Concepts

```
Location → Piano → MaintenanceSchedule (from Template) → WorkOrder → MaintenanceLog
                                                                    ↳ PartUsed
                                                                    ↳ ConditionReading
```

1. **Locations** group pianos by building or site.
2. **Pianos** are the assets. Each gets a unique QR code token for public request submissions.
3. **Schedule Templates** are reusable task blueprints (e.g., "Annual Tuning — every 365 days"). Apply one template to many pianos in bulk.
4. **Maintenance Schedules** are the per-piano instances of those templates. They define what recurring task needs to happen and how often.
5. **Work Orders** are generated automatically (via management command) when a scheduled task is overdue or has never been completed. They can also be created manually or from a public maintenance request.
6. **Maintenance Logs** are written when a technician closes a work order — capturing hours worked, parts used, and a condition reading of the piano.

---

## Project Structure

```
piano_maintainer/          Django project config (settings, URLs)
maintenance/
  models.py                All 10 domain models
  api.py                   DRF ViewSets (REST API)
  serializers.py           API serializers
  views.py                 Server-rendered views (login, QR form, dashboard)
  urls.py                  URL routing
  admin.py                 Django Admin customizations
  management/commands/
    generate_work_orders.py  CLI command: auto-create overdue work orders
frontend/
  src/
    App.jsx                Top-level router + nav
    pages/
      PianosPage.jsx       Piano inventory CRUD
      MaintenancePage.jsx  Schedules & templates (tabbed)
    components/
      PianoFormModal.jsx
      ScheduleFormModal.jsx
      TemplateFormModal.jsx
      ApplyTemplateModal.jsx
```

---

## Getting Started

### Backend

```bash
cd piano_maintainer
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # creates your first Technician account
python manage.py runserver         # http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

### Generate Work Orders (CLI)

Run this on a schedule (e.g., daily cron) to auto-create work orders for overdue maintenance:

```bash
python manage.py generate_work_orders
```

The command checks every active `MaintenanceSchedule`, calculates when the task is next due (based on `interval_days` and the date of the last completed work order), and creates a new open `WorkOrder` if none exists yet.

---

## Data Models

| Model | Purpose |
|-------|---------|
| `Location` | Physical site (building, address) |
| `Piano` | Asset record — brand, model, type, serial #, QR token |
| `Technician` | Custom user — extends Django's AbstractUser |
| `ScheduleTemplate` | Reusable task blueprint (task type, interval, warning window) |
| `MaintenanceSchedule` | Per-piano recurring task (linked to a template or manual) |
| `WorkOrder` | Job ticket — status, priority, type, assigned tech, due date |
| `MaintenanceLog` | Completed work record — hours, notes, linked to work order |
| `ConditionReading` | Snapshot of piano health (pitch offset, humidity, temp, rating) |
| `Part` | Inventory item — cost, stock qty, reorder threshold |
| `PartUsed` | Parts consumed on a specific log entry |
| `MaintenanceRequest` | Public submission via QR code — no login required |

---

## API Endpoints

All endpoints are under `/api/` and served by Django REST Framework.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/locations/` | List or create locations |
| GET/POST/PUT/DELETE | `/api/pianos/` | Full piano CRUD |
| GET/POST/PUT/DELETE | `/api/schedules/` | Maintenance schedule CRUD |
| GET/POST/PUT/DELETE | `/api/schedule-templates/` | Template CRUD |
| POST | `/api/schedule-templates/{id}/apply_to_pianos/` | Bulk-apply template to selected pianos |

---

## Implemented Features

- [x] Piano inventory (CRUD) with location grouping and type badges
- [x] Maintenance schedule management (CRUD) per piano
- [x] Schedule templates for DRY recurring task definitions
- [x] Bulk template application across multiple pianos
- [x] Automatic work order generation (management command)
- [x] QR code token per piano for public maintenance requests
- [x] Public maintenance request form (no login required)
- [x] Django Admin for all models
- [x] Backend models for: work orders, logs, parts, condition readings, requests

---

## Feature Roadmap — What's Needed for Full CMMS

The backend data models exist for most of these features, but the React frontend and API endpoints need to be built out.

### P0 — Core Workflow (Must Have)

| # | Feature | Notes |
|---|---------|-------|
| 1 | **Work Order List & Detail UI** | View/filter all work orders by status, priority, piano, tech. Currently no frontend page. |
| 2 | **Work Order Creation (manual)** | Create ad-hoc work orders from the UI (not just via CLI). |
| 3 | **Work Order Assignment** | Assign/reassign a work order to a technician from the UI. |
| 4 | **Maintenance Log Entry** | Technician closes a work order by filing a log: hours worked, work performed, notes. |
| 5 | **Authentication UI** | Login/logout flow in React. Currently auth is Django-session only, with no React login page. API is currently open (`AllowAny`). |
| 6 | **Dashboard with KPIs** | Open work order count, overdue count, upcoming (within warning window), completion rate. |

### P1 — Operations (High Value)

| # | Feature | Notes |
|---|---------|-------|
| 7 | **Condition Readings UI** | Log pitch offset, humidity, temperature, and overall rating when completing a work order. |
| 8 | **Piano Detail Page** | Full history: work order timeline, condition trend charts, schedule overview, recent logs. |
| 9 | **Parts Inventory Management** | CRUD for parts stock, unit cost, reorder thresholds. Show low-stock alerts. |
| 10 | **Parts Usage on Work Orders** | Attach parts consumed (and qty) to a maintenance log; auto-decrement stock. |
| 11 | **Technician Management** | Admin can create/deactivate technicians, set roles, view workload. |
| 12 | **Work Order Status Workflow** | Move WO through: Open → In Progress → Complete / Cancelled with timestamps. |
| 13 | **Maintenance Request Queue** | List incoming public requests, assign them to a work order, mark resolved. |

### P2 — Scheduling Intelligence

| # | Feature | Notes |
|---|---------|-------|
| 14 | **Automated WO Generation (scheduled)** | Replace manual CLI command with a Django-Q / Celery beat task running on a cron. |
| 15 | **Overdue & Upcoming Alerts** | Email or in-app notifications when a task enters the warning window or goes overdue. |
| 16 | **Due Date Calendar View** | Calendar UI showing upcoming and overdue scheduled tasks. |
| 17 | **Schedule Pause / Skip** | Pause a schedule (e.g., piano out of service) or skip one cycle without deleting. |

### P3 — Reporting & Analytics

| # | Feature | Notes |
|---|---------|-------|
| 18 | **Maintenance Cost Reporting** | Total labor + parts cost per piano, per location, per date range. |
| 19 | **Technician Workload Report** | Hours logged, WOs completed, avg completion time per technician. |
| 20 | **Condition Trend Charts** | Pitch offset / humidity / temperature over time per piano. |
| 21 | **Compliance / PM Completion Rate** | % of scheduled PMs completed on time over a rolling period. |
| 22 | **Export to CSV / PDF** | Export any report or work order list. |

### P4 — Platform & UX Polish

| # | Feature | Notes |
|---|---------|-------|
| 23 | **QR Code Generation UI** | Display/print a piano's QR code from the piano detail page. |
| 24 | **Mobile-Responsive Design** | Technicians need to log work on phones in the field. |
| 25 | **Photo Attachments** | Attach before/after photos to a work order or log entry. |
| 26 | **Search & Filter** | Global search across pianos, work orders, and logs. |
| 27 | **Multi-Tenant / Org Support** | Isolate data per organization for a SaaS offering. |
| 28 | **API Authentication** | JWT or token auth on all DRF endpoints (currently `AllowAny`). |
| 29 | **Audit Log** | Track who changed what and when on work orders and assets. |
| 30 | **PostgreSQL Migration** | Swap SQLite for Postgres for production readiness. |

---

## Development Notes

- The React dev server (`localhost:5173`) proxies API calls to Django (`localhost:8000`). CORS is pre-configured.
- `Technician` is the custom `AUTH_USER_MODEL`. Never reference Django's built-in `User` directly.
- `generate_work_orders` uses `warning_days_before` to set `due_date` on the work order so it surfaces before the actual deadline.
- `MaintenanceRequest` submissions require only the piano's `qr_code_token` — no login — making public reporting safe and easy.
