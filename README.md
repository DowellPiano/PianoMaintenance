# Piano Maintainer — CMMS for Pianos

A Computerized Maintenance Management System (CMMS) built for piano technicians and facilities managers. Modeled after [Limble CMMS](https://limblecmms.com), Piano Maintainer handles preventive maintenance scheduling, work order management, technician dispatch, and parts tracking — purpose-built for piano fleets in schools, venues, and studios.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3 · Django 5.2 · Django REST Framework |
| Frontend | React 18 · Vite · React Router |
| Database | SQLite (dev) |
| Auth | Token auth via DRF (custom `Technician` user model) |

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
  urls.py                  URL routing
  admin.py                 Django Admin customizations
  management/commands/
    generate_work_orders.py  CLI command: auto-create overdue work orders
frontend/
  src/
    App.jsx                Top-level router + nav + auth guards
    AuthContext.jsx        Token auth context (login, logout, isAuthenticated)
    api.js                 Authenticated fetch wrapper
    pages/
      LoginPage.jsx        Login form
      DashboardPage.jsx    KPI cards + urgent work orders
      PianosPage.jsx       Piano inventory CRUD
      PianoProfilePage.jsx Piano detail — history, schedules, photos
      LocationsPage.jsx    Location list CRUD
      LocationProfilePage.jsx  Location detail with piano list
      MaintenancePage.jsx  Schedules & templates (tabbed)
      WorkOrdersPage.jsx   Work order list with filters + status actions
      SchedulePage.jsx     Calendar view of schedules and work orders
    components/
      WorkOrderFormModal.jsx   Create/edit work orders
      LogEntryModal.jsx        Log hours + notes when completing a WO
      PianoFormModal.jsx
      LocationFormModal.jsx
      ScheduleFormModal.jsx
      TemplateFormModal.jsx
      ApplyTemplateModal.jsx
      MonthCalendar.jsx
```

---

## Getting Started

### Backend

```bash
cd piano_maintainer
pip3 install -r requirements.txt   # run this every time you pull a new branch
python manage.py migrate
python manage.py createsuperuser   # creates your first Technician account
python manage.py runserver         # http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install                        # run this every time you pull a new branch
npm run dev                        # http://localhost:5173
```

### Task Queue (required for scheduled automation)

P2+ features use `django-q2` for automated work order generation and alerts.
Run this in a third terminal alongside the backend:

```bash
python manage.py qcluster
```

Without `qcluster` running, scheduled tasks (daily WO generation, alert creation)
will not fire. Manual work order generation still works via CLI:

```bash
python manage.py generate_work_orders
```

### Pulling a new branch — checklist

Every time you switch branches or pull new changes:

```bash
pip3 install -r requirements.txt   # picks up any new Python packages
python manage.py migrate           # applies any new database migrations
cd frontend && npm install         # picks up any new JS packages
```

Skipping these steps is the most common cause of "missing package" or
"table does not exist" errors after a branch switch.

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
| POST | `/api/auth/login/` | Login — returns token + user |
| POST | `/api/auth/logout/` | Invalidate token |
| GET | `/api/auth/me/` | Current user info |
| GET | `/api/dashboard/` | KPI counts + urgent work orders |
| GET/POST | `/api/locations/` | List or create locations |
| GET/PUT/DELETE | `/api/locations/{id}/` | Location detail |
| GET | `/api/locations/{id}/profile/` | Location + all pianos |
| GET/POST | `/api/pianos/` | Full piano CRUD |
| GET/PUT/DELETE | `/api/pianos/{id}/` | Piano detail |
| GET | `/api/pianos/{id}/profile/` | Piano + work orders + schedules + photos |
| GET/POST/PUT/DELETE | `/api/schedules/` | Maintenance schedule CRUD |
| GET/POST/PUT/DELETE | `/api/schedule-templates/` | Template CRUD |
| POST | `/api/schedule-templates/{id}/apply_to_pianos/` | Bulk-apply template to selected pianos |
| GET/POST | `/api/work-orders/` | Work order list (filterable) + create |
| GET/PUT/DELETE | `/api/work-orders/{id}/` | Work order detail |
| POST | `/api/work-orders/{id}/start/` | Transition Open → In Progress |
| POST | `/api/work-orders/{id}/complete/` | Complete WO + create maintenance log |
| GET/POST | `/api/maintenance-logs/` | List or create maintenance logs |
| GET/POST | `/api/technicians/` | Technician list |
| GET/POST | `/api/photos/` | Photo management |
| GET | `/api/calendar-events/` | Unified calendar (WOs + schedules) by date range |

---

## Implemented Features

### Foundation
- [x] Piano inventory (CRUD) with location grouping, type badges, and photo management
- [x] Location management with per-location piano roster
- [x] Piano profile page — work order history, active schedules, photos
- [x] Maintenance schedule management (CRUD) per piano
- [x] Schedule templates for DRY recurring task definitions
- [x] Bulk template application across multiple pianos
- [x] Automatic work order generation (management command)
- [x] Calendar view — unified WOs and scheduled tasks by month
- [x] QR code token per piano for public maintenance requests
- [x] Django Admin for all models

### P0 — Core Workflow ✅ Complete
- [x] Token-based authentication (login / logout / session persistence)
- [x] Protected routes — unauthenticated users redirected to login
- [x] Dashboard with live KPI cards (Open, In Progress, Overdue, Due Soon, Completed This Month)
- [x] Work order list with status, priority, and keyword filters
- [x] Work order creation and editing via modal
- [x] Status transitions: Open → In Progress → Complete → Cancelled
- [x] Maintenance log entry on completion (hours worked, work performed, notes)
- [x] Overdue work order highlighting
- [x] Technician assignment on work orders

### P1 — Operations ✅ Complete
- [x] Condition readings on log entry — pitch before (¢), pitch after (¢), humidity, temperature, overall rating
- [x] Parts inventory CRUD — name, part #, supplier, unit cost, stock qty, reorder threshold, low-stock alerts
- [x] Parts used on work orders — attach parts to log entry, stock auto-decrements
- [x] Technician management — create, deactivate, reactivate, safe hard delete
- [x] Team management — create teams, assign manager, assign technicians
- [x] Maintenance request queue — list, filter, one-click assign to work order, live nav badge

---

## Feature Roadmap — What's Needed for Full CMMS

### ~~P0 — Core Workflow~~ ✅ Complete
### ~~P1 — Operations~~ ✅ Complete

### P2 — Scheduling Intelligence

### P2 — Scheduling Intelligence

| # | Feature | Notes |
|---|---------|-------|
| 13 | **Automated WO Generation (scheduled)** | Replace manual CLI command with a Django-Q / Celery beat task running on a cron. |
| 14 | **Overdue & Upcoming Alerts** | Email or in-app notifications when a task enters the warning window or goes overdue. |
| 15 | **Due Date Calendar View** | Calendar UI showing upcoming and overdue scheduled tasks. Already scaffolded — needs polish and full integration. |
| 16 | **Schedule Pause / Skip** | Pause a schedule (e.g., piano out of service) or skip one cycle without deleting. |

### P3 — Reporting & Analytics

| # | Feature | Notes |
|---|---------|-------|
| 18 | **Maintenance Cost Reporting** | Total labor + parts cost per piano, per location, per date range. |
| 19 | **Technician Workload Report** | Hours logged, WOs completed, avg completion time per technician. |
| 20 | **Condition Trend Charts** | Pitch before/after and humidity/temperature over time per piano. |
| 21 | **Humidity/Pitch Correlation Table** | Per-piano table bucketing pitch drift by humidity range, enabling technicians to tune strategically and maintain a 0¢ average over a rolling 365-day window. Requires 6–12 months of condition readings to be statistically useful. Endpoint: `GET /api/pianos/{id}/pitch-humidity-table/` |
| 22 | **Compliance / PM Completion Rate** | % of scheduled PMs completed on time over a rolling period. |
| 23 | **Export to CSV / PDF** | Export any report or work order list. |

### P4 — Platform & UX Polish

| # | Feature | Notes |
|---|---------|-------|
| 23 | **QR Code Generation UI** | Display/print a piano's QR code from the piano detail page. |
| 24 | **Mobile-Responsive Design** | Technicians need to log work on phones in the field. |
| 25 | **Photo Attachments** | Attach before/after photos to a work order or log entry. |
| 26 | **Search & Filter** | Global search across pianos, work orders, and logs. |
| 27 | **Multi-Tenant / Org Support** | Isolate data per organization for a SaaS offering. |
| 28 | **API Authentication** | Harden token auth — add token expiry, rotation, and refresh endpoints. |
| 29 | **Audit Log** | Track who changed what and when on work orders and assets. |
| 30 | **PostgreSQL Migration** | Swap SQLite for Postgres for production readiness. |

---

## Development Notes

- The React dev server (`localhost:5173`) proxies API calls to Django (`localhost:8000`). CORS is pre-configured.
- `Technician` is the custom `AUTH_USER_MODEL`. Never reference Django's built-in `User` directly.
- `generate_work_orders` uses `warning_days_before` to set `due_date` on the work order so it surfaces before the actual deadline.
- `MaintenanceRequest` submissions require only the piano's `qr_code_token` — no login — making public reporting safe and easy. On submission, a Work Order is created automatically — technicians never need to manually convert requests.
- **New Python package added to a branch?** Always run `pip3 install -r requirements.txt` after pulling. Forgetting this is the #1 cause of `ModuleNotFoundError` on server start.
- **New migration added to a branch?** Always run `python manage.py migrate` after pulling. Forgetting this causes `OperationalError: no such table` or `column does not exist` errors.
- **Running scheduled tasks locally?** Start `python manage.py qcluster` in a separate terminal. Without it, automated WO generation and alerts will queue but never execute.
