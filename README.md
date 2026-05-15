# Piano Maintainer — CMMS for Pianos

A Computerized Maintenance Management System (CMMS) built for piano technicians and facilities managers. Modeled after [Limble CMMS](https://limblecmms.com), Piano Maintainer handles preventive maintenance scheduling, work order management, service visits, condition tracking, and parts inventory — purpose-built for piano fleets in schools, venues, and studios.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 · Django 6.0 · Django REST Framework |
| Frontend | Django Templates · HTMX 2.0.4 |
| Database | SQLite (dev) |
| Auth | Django session auth · Custom `Technician` user model |

---

## How It Works

### Core Concepts

```
Organization → Venue → Piano → MaintenanceSchedule → WorkOrder → MaintenanceLog
                          ↑                                         ↳ PartUsed
                         Tag                                        ↳ ConditionReading
                                  ServiceVisit ──→ WorkOrder(s)
```

1. **Organizations** are the administrative owners (a school district, a church, a concert hall).
2. **Venues** are the physical locations a technician drives to. Each venue belongs to one organization.
3. **Pianos** are the assets. Each gets a unique QR code token for public maintenance request submissions.
4. **Tags** are free-form labels you can attach to any piano for custom grouping and filtering (e.g., "Concert", "Practice Room", "Needs Rebuild").
5. **Schedule Templates** are reusable task blueprints (e.g., "Annual Tuning — every 365 days"). Apply one template to many pianos in bulk.
6. **Maintenance Schedules** are the per-piano instances of those templates, defining what recurring task needs to happen and how often.
7. **Service Visits** represent a single trip to a venue. Multiple work orders can be linked to one visit.
8. **Work Orders** are generated automatically when a scheduled task is overdue, or created manually, or from a public maintenance request.
9. **Maintenance Logs** are written when a technician closes a work order — capturing hours worked, parts used, and an optional condition reading.

---

## Project Structure

```
piano_maintainer/              Django project config (settings, URLs)
maintenance/
  models.py                    18 domain models
  views.py                     55 view functions (template-based UI)
  api.py                       DRF ViewSets (REST API)
  serializers.py               API serializers
  urls.py                      API URL routing
  admin.py                     Django Admin customizations
  forms.py                     Django forms
  management/commands/
    generate_work_orders.py    CLI command: auto-create overdue work orders
  templates/
    base.html                  Shared layout with sidebar nav
    maintenance/
      35 page templates        Full CRUD pages for all entities
      partials/                HTMX tab partials for piano detail
  static/
    css/base.css               Custom CSS design system
```

---

## Getting Started

```bash
pip3 install -r requirements.txt
python3 manage.py migrate
python3 manage.py createsuperuser    # creates your first Technician account
python3 manage.py runserver          # http://localhost:8000
```

### Pulling a new branch — checklist

```bash
pip3 install -r requirements.txt     # picks up any new Python packages
python3 manage.py migrate            # applies any new database migrations
```

### Demo data reset

For deployments where the app should open with realistic sample data, run:

```bash
python3 manage.py reset_demo_data --yes
```

This replaces existing app data with an editable demo account and a realistic piano-service dataset: organizations, venues, pianos, schedules, work orders, logs, condition readings, requests, and inventory.

Demo login:

```text
username: demo-admin
password: DemoPass123
```

For a public demo environment, run the command as part of your deploy/release/startup script after migrations. Users can change the demo records while the app is running; running the command again resets everything back to the seeded state.

### Automated work order generation

The `generate_work_orders` management command creates work orders for overdue or upcoming maintenance schedules. It is intentionally separate from page views, so browsing Work Orders or Schedule does not create records as a side effect:

```bash
python3 manage.py generate_work_orders           # run for real
python3 manage.py generate_work_orders --dry-run  # preview without saving
```

Run it hourly from cron:

```cron
0 * * * * cd /Users/tom/Desktop/Limble\ Clone/PianoMaintenance && /usr/bin/env python3 manage.py generate_work_orders >> /tmp/piano_generate_work_orders.log 2>&1
```

---

## Data Models

| Model | Purpose |
|-------|---------|
| `Tag` | Free-form label for custom piano grouping and filtering |
| `Organization` | Administrative owner (school, church, concert hall) |
| `Venue` | Physical location a technician drives to; belongs to an Organization |
| `Piano` | Asset record — make, model, type, serial #, QR token, tags, condition state |
| `Technician` | Custom user — extends Django's AbstractUser |
| `Team` | Group of technicians with a manager |
| `ScheduleTemplate` | Reusable task blueprint (task type, interval, warning window) |
| `MaintenanceSchedule` | Per-piano recurring task (linked to a template or manual) |
| `ServiceVisit` | A single trip to a venue; links multiple work orders |
| `WorkOrder` | Job ticket — status, priority, type, assigned tech, due date |
| `MaintenanceLog` | Completed work record — hours, notes, linked to work order |
| `ConditionReading` | Snapshot of piano health (10 component ratings, pitch, humidity, temp) |
| `Part` | Inventory item — cost, stock qty, reorder threshold |
| `PartUsed` | Parts consumed on a specific log entry |
| `MaintenanceRequest` | Public submission via QR code — no login required |
| `Photo` | Image attached to a piano or work order |
| `Alert` | In-app notification for overdue/due-soon work orders |
| `Attachment` | File attachment on a work order |

---

## Pages & Features

### Dashboard
- KPI cards: Open, In Progress, Overdue, Pending Requests, Pianos, Venues, Organizations
- Completed this month count
- Recent work orders list

### Pianos
- Card grid with photos, condition dots, and tuning due dates
- Filter by organization, venue, type, and tag
- Search by name, make, serial number, or tag
- Soft delete (deactivate) from detail page — data preserved, hidden from lists
- Inline tag management with autocomplete on detail page
- HTMX tabbed detail view: Overview, Work Orders, Maintenance, Condition
- Photo gallery with profile photo selection
- QR code URL for public maintenance requests
- CSV import and export

### Organizations
- Card grid with venue counts
- Full CRUD (create, edit, hard delete)
- Delete blocked if venues still exist (PROTECT FK safety)
- Detail page shows linked venues

### Venues
- List with organization grouping and piano counts
- Full CRUD
- Detail page shows linked pianos and service visits

### Service Visits
- Represents one trip to a venue
- Link multiple work orders to a single visit
- Completion flow: time in/out, miles driven, notes
- Filter by venue, technician, date range

### Work Orders
- List with status/priority/type filters and search
- Create manually, from schedule, or from public request
- Status transitions: Open → In Progress → Complete
- Completion flow: hours worked, work performed, optional condition reading
- Technician assignment

### Maintenance Schedules & Templates
- Reusable schedule templates (task type, interval, warning window)
- Bulk-apply templates to multiple pianos
- Per-piano schedule management with pause/resume and delete
- Automatic work order generation for overdue schedules

### Technicians
- Active technician list with open work order counts
- Work report page with date range filtering
- Totals row (hours, work orders)
- CSV export

### Parts Inventory
- CRUD for parts with cost, stock, and reorder threshold
- Parts attached to maintenance logs on work order completion

### Reports
- Work order CSV export
- Piano CSV export
- Technician work report with date filtering and CSV export

### Public Maintenance Requests
- QR code per piano links to a public form (no login required)
- Submissions auto-create a work order

---

## API

A full REST API coexists with the template UI under `/api/`, powered by Django REST Framework. Key endpoints:

| Area | Endpoints |
|------|-----------|
| Auth | Login, logout, current user |
| Dashboard | KPI counts + urgent work orders |
| Organizations | CRUD |
| Venues | CRUD |
| Pianos | CRUD, profile (detail + history), CSV export |
| Work Orders | CRUD, status transitions (start, complete) |
| Schedules | CRUD for schedules and templates, bulk apply |
| Maintenance Logs | List and create |
| Technicians | List, stats, CSV export |
| Service Visits | CRUD |
| Reports | Technician stats, piano export, work order export |
| Calendar | Unified WO + schedule events by date range |

---

## Development Notes

- **No separate frontend build step.** The UI is Django templates + HTMX. Just run `python3 manage.py runserver`.
- `Technician` is the custom `AUTH_USER_MODEL`. Never reference Django's built-in `User` directly.
- `generate_work_orders` uses `warning_days_before` to create work orders before the actual deadline.
- `MaintenanceRequest` submissions require only the piano's `qr_code_token` — no login. On submission, a Work Order is created automatically.
- `Piano.is_active` powers soft delete — deactivated pianos are hidden from lists but data is preserved.
- `Piano.tags` is a M2M to `Tag` — use tags for any custom grouping (building wing, priority tier, client name, etc.).
- `Organization` uses `PROTECT` on its venue FK — you must remove all venues before deleting an organization.
- `ConditionReading.update_piano_current_state()` copies readings to denormalized fields on Piano for fast display.
- `Piano.advance_schedule(task_type, completed_date)` computes the next due date when a work order is completed.

---

## Supabase Public API Hardening

Supabase can expose tables in the `public` schema through its REST API if the
`anon` or `authenticated` database roles have grants. This Django app does not
use Supabase's client-side database API; it talks to Postgres from the server.

Migration `maintenance.0013_lock_down_supabase_public_api` enables row-level
security on public tables and revokes default table, sequence, and function
access from Supabase API roles. Run it in production after deploying:

```bash
python manage.py migrate maintenance 0013
```

If you later add a deliberate Supabase REST/client feature, create narrow RLS
policies for only the specific tables and actions that feature needs.
