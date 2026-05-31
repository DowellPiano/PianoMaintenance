# Overtone — CMMS for Pianos

A Computerized Maintenance Management System (CMMS) built for piano technicians and facilities managers. Modeled after [Limble CMMS](https://limblecmms.com), Overtone handles preventive maintenance scheduling, work order management, service visits, condition tracking, and parts inventory — purpose-built for piano fleets in schools, venues, and studios.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 · Django 5.2 · Django REST Framework |
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
    bootstrap_company.py       CLI command: create a company + initial admin
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

### Fresh SaaS bootstrap

For a brand-new SaaS environment, create the first company and company admin with:

```bash
python3 manage.py bootstrap_company \
  --company-name "Acme Piano Service" \
  --admin-username admin \
  --admin-password "change-me-now" \
  --admin-email admin@example.com \
  --first-name Acme \
  --last-name Admin
```

This creates:
- the `Company`
- a `CompanySettings` row
- an initial active admin + technician membership for the chosen user

On the `SaaS` branch, this is the intended first-account path. Public self-service signup is disabled; additional users should join by company invitation after the initial admin is bootstrapped.

### Automated work order generation

The `generate_work_orders` management command creates work orders for overdue or upcoming maintenance schedules. It is intentionally separate from page views, so browsing Work Orders or Schedule does not create records as a side effect:

```bash
python3 manage.py generate_work_orders           # run for real
python3 manage.py generate_work_orders --dry-run  # preview without saving
```

Run it hourly from cron:

```cron
0 * * * * cd /path/to/Overtone && /usr/bin/env python3 manage.py generate_work_orders >> /tmp/overtone_generate_work_orders.log 2>&1
```

On Render, create a separate Cron Job service from the same GitHub repo and
branch as the web service. Use the same environment variables or link the same
environment group as the web service so the command reaches the production
database and storage configuration.

Recommended Render Cron Job settings:

```text
Name: overtone-generate-work-orders
Branch: SaaS
Build Command: pip install -r requirements.txt
Command: python manage.py generate_work_orders
Schedule: 0 * * * *
```

Render cron schedules run in UTC. Manually trigger the job once after creation
and confirm the logs end with the command summary.

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

### SaaS tenancy rollout

The `SaaS` branch is now the clean multi-company product track. It should be treated as a fresh-database deployment target rather than a compatibility layer for the older private-use environment. The current implemented foundation includes:

- `Company`, `CompanyMembership`, `CompanyInvitation`, and `AuditLog`
- active-company request/session context and a company switcher
- required company ownership fields on the core operational models
- local password reset views/templates
- invitation acceptance flow for adding users to a company
- company-scoped query enforcement across the main UI flows
- no default-company autofill or silent tenant fallback in the runtime model layer
- authenticated photo delivery for company media, with local file streaming in dev and short-lived signed URLs in object storage
- tenant-admin setup progress, invitation resend/revoke history, and company-scoped member activation controls in the settings and users flows

Use local SQLite while validating these changes:

```bash
env SECRET_KEY='dev-secret-key' DEBUG=True DATABASE_URL='sqlite:////tmp/piano_saas.sqlite3' python3 manage.py migrate
env SECRET_KEY='dev-secret-key' DEBUG=True DATABASE_URL='sqlite:////tmp/piano_saas_test.sqlite3' python3 manage.py test maintenance
```

This branch should be verified locally before any production Postgres deployment is considered.
For private media, optional production tuning:

```bash
PRIVATE_MEDIA_URL_TTL=900
```

Operational commands for the SaaS branch:

```bash
# Generate work orders for every company
python3 manage.py generate_work_orders

# Target one tenant while testing automation behavior
python3 manage.py generate_work_orders --company-slug=default-company
python3 manage.py generate_work_orders --company-id=1

# Expire stale invitations before they clutter the admin UX
python3 manage.py expire_invitations

# See whether the current environment still looks like local dev or is shaped for SaaS production
python3 manage.py saas_readiness_report

# Run Django's production deployment checks
python3 manage.py check --deploy
```

Recommended production env vars for the SaaS branch:

```bash
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=app.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com
DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require
DATABASE_CONN_MAX_AGE=600
DATABASE_SSL_REQUIRE=True
DEFAULT_FROM_EMAIL=noreply@example.com
EMAIL_NOTIFICATIONS_ENABLED=True
EMAIL_BACKEND=anymail.backends.resend.EmailBackend
RESEND_API_KEY=...
EMAIL_TIMEOUT=10
PRIVATE_MEDIA_URL_TTL=900
SUPABASE_S3_REQUIRED=True
SUPABASE_S3_ACCESS_KEY_ID=...
SUPABASE_S3_SECRET_ACCESS_KEY=...
SUPABASE_S3_BUCKET=...
SUPABASE_S3_ENDPOINT=...
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

Before launch, validate the production environment with a real Postgres database,
real SMTP credentials, and real Supabase/S3-compatible storage credentials:

For Supabase Postgres, use the direct or pooler connection string supplied by
Supabase and append `?sslmode=require` if the URL does not already include SSL
parameters.

For Supabase Storage, use Supabase S3-compatible storage credentials, not the
publishable client key. With `SUPABASE_S3_REQUIRED=True`, Django fails startup
if the storage bucket, endpoint, access key, or secret key is missing. This
prevents production uploads from falling back to the local `media/` directory.
Supabase S3 endpoints use the form
`https://project-ref.storage.supabase.co/storage/v1/s3`.

For production email, use Resend over HTTPS rather than SMTP. Create a Resend
API key with sending access, verify the sending domain or sender address in
Resend, and set `EMAIL_BACKEND=anymail.backends.resend.EmailBackend` with
`RESEND_API_KEY` in the deployment environment. Keep `DEFAULT_FROM_EMAIL` aligned
with the verified Resend sender.

```bash
python3 manage.py migrate
python3 manage.py bootstrap_company \
  --company-name "Acme Piano Service" \
  --admin-username admin \
  --admin-password "replace-with-a-real-temporary-password" \
  --admin-email admin@example.com
python3 manage.py check --deploy
python3 manage.py saas_readiness_report
python3 manage.py collectstatic --noinput
```

The readiness report should have no warnings before a real customer tenant is
created. If Django is behind a proxy or load balancer, set
`USE_X_FORWARDED_PROTO=True` only when the proxy reliably sends
`X-Forwarded-Proto: https`.
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
