# Overtone — CMMS for Pianos

A Computerized Maintenance Management System (CMMS) built for piano technicians and facilities managers. Modeled after [Limble CMMS](https://limblecmms.com), Overtone handles preventive maintenance scheduling, work order management, condition tracking, parts inventory, and public service requests — purpose-built for piano fleets in schools, venues, and studios.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 · Django 5.2 |
| Frontend | Django Templates · HTMX 2.0.4 |
| Database | SQLite (local development) · PostgreSQL (production) |
| Auth | Django session auth · Custom `Technician` user model · Company memberships |

---

## How It Works

### Core Concepts

```
Company → Organization → Venue → Piano → MaintenanceSchedule → WorkOrder → MaintenanceLog
                                  ↑                                         ↳ PartUsed
                                 Tag                                        ↳ ConditionReading
Company → CompanyMembership → Technician
```

1. **Companies** are the tenant boundary. Operational records belong to exactly one company.
2. **Company Memberships** give users company-specific admin and technician roles.
3. **Organizations** are the administrative owners or client accounts (a school district, a church, a concert hall).
4. **Venues** are the physical locations a technician drives to. A venue may belong to an organization.
5. **Pianos** are the assets. Each gets a unique QR code token for public maintenance request submissions.
6. **Tags** are free-form labels you can attach to any piano for custom grouping and filtering (e.g., "Concert", "Practice Room", "Needs Rebuild").
7. **Schedule Templates** are reusable task blueprints (e.g., "Annual Tuning — every 365 days"). Apply one template to many pianos in bulk.
8. **Maintenance Schedules** are the per-piano instances of those templates, defining what recurring task needs to happen and how often.
9. **Work Orders** are generated automatically from scheduled maintenance, created manually, or created from a public maintenance request.
10. **Maintenance Logs** capture technician hours, work performed, parts used, and optional condition readings.

---

## Project Structure

```
piano_maintainer/              Django project config (settings, URLs)
maintenance/
  models.py                    Domain and tenancy models
  views.py                     Template-based UI and workflow handlers
  services.py                  Scheduled generation and setup-progress logic
  tenancy.py                   Active-company access helpers
  email_notifications.py       Operational email notifications
  admin.py                     Django Admin customizations
  forms.py                     Django forms
  management/commands/
    generate_work_orders.py    CLI command: auto-create overdue work orders
    bootstrap_company.py       CLI command: create a company + initial admin
  templates/
    base.html                  Shared layout with sidebar nav
    maintenance/
      page templates           CRUD and workflow pages
      partials/                HTMX and reusable UI partials
  static/
    css/base.css               Custom CSS design system
```

---

## Getting Started

```bash
pip3 install -r requirements.txt
python3 manage.py migrate
python3 manage.py bootstrap_company \
  --company-name "Acme Piano Service" \
  --admin-username admin \
  --admin-password "change-me-now"
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
Name: overtone-daily-operations
Branch: SaaS
Build Command: pip install -r requirements.txt
Command: python manage.py run_daily_operations
Schedule: 0 6 * * *
```

Render cron schedules run in UTC. Manually trigger the job once after creation
and confirm the logs show both a verified backup and the work-order generation
summary. The two jobs are independent: work-order generation is still attempted
if the backup fails, but the cron run exits unsuccessfully so Render sends its
failure notification.

---

## Data Models

| Model | Purpose |
|-------|---------|
| `Company` | Tenant root for company-owned data |
| `CompanyMembership` | Company-specific admin and technician roles for a user |
| `CompanyInvitation` | Time-limited invitation to join a company |
| `AuditLog` | Company-scoped record of important user and system activity |
| `CompanySettings` | Company profile, contact information, and labor defaults |
| `Tag` | Free-form label for custom piano grouping and filtering |
| `Organization` | Administrative owner (school, church, concert hall) |
| `Venue` | Physical location a technician drives to; may belong to an Organization |
| `Piano` | Asset record — make, model, type, serial #, QR token, tags, condition state |
| `Technician` | Custom user — extends Django's AbstractUser |
| `ScheduleTemplate` | Reusable task blueprint (task type, interval, warning window) |
| `MaintenanceSchedule` | Per-piano recurring task (linked to a template or manual) |
| `WorkOrder` | Job ticket — status, priority, type, assigned tech, due date |
| `MaintenanceLog` | Technician work record — hours, notes, linked to work order |
| `ConditionReading` | Snapshot of piano health (10 component ratings, pitch, humidity, temp) |
| `Part` | Inventory item — cost, stock qty, reorder threshold |
| `PartUsed` | Parts consumed on a specific log entry |
| `MaintenanceRequest` | Public submission via QR code — no login required |
| `Photo` | Image attached to a piano or work order |

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
- Deleting an organization preserves its venues and clears their organization association
- Detail page shows linked venues

### Venues
- List with organization grouping and piano counts
- Full CRUD
- Detail page shows linked pianos and open work-order counts

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
- Create and edit parts with cost, stock, and reorder threshold
- Parts attached to maintenance logs on work order completion

### Reports
- Work order CSV export
- Piano CSV export
- Technician work report with date filtering and CSV export

### Public Maintenance Requests
- QR code per piano links to a public form (no login required)
- Submissions auto-create a work order

---

## Application Interface

The current application is a server-rendered Django and HTMX UI. It does not expose a Django REST Framework API or an `/api/` route. CSV imports and exports are provided through authenticated UI endpoints. Supabase's client-side database API is intentionally locked down; Django accesses PostgreSQL from the server.

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
- a superuser-only platform boundary for both Django admin and the product platform console; company admins are not Django staff

Use local SQLite while validating these changes:

```bash
env SECRET_KEY='dev-secret-key' DEBUG=True DATABASE_URL='sqlite:////tmp/piano_saas.sqlite3' python3 manage.py migrate
env SECRET_KEY='dev-secret-key' \
  DEBUG=True \
  DATABASE_URL='sqlite:////tmp/piano_saas_test.sqlite3' \
  SUPABASE_S3_REQUIRED=False \
  SUPABASE_S3_ACCESS_KEY_ID='' \
  SUPABASE_S3_SECRET_ACCESS_KEY='' \
  SUPABASE_S3_BUCKET='' \
  SUPABASE_S3_ENDPOINT='' \
  python3 manage.py test maintenance
```

Run the isolated local checks before deploying changes to production PostgreSQL.
For private media, optional production tuning:

```bash
PRIVATE_MEDIA_URL_TTL=900
```

### Continuous integration

GitHub Actions runs Django checks, migration-drift detection, and the complete
test suite for every push to `SaaS`, every pull request targeting `SaaS`, and
manual workflow dispatches. CI uses Python 3.12, a temporary SQLite database,
temporary filesystem media storage, Django's in-memory email backend, and no
Supabase, Backblaze, Resend, or Sentry credentials.

The workflow is defined in `.github/workflows/tests.yml`. Keep the `Django tests
/ Python 3.12` check green before deploying a commit or merging a pull request.
In the Render service settings, set **Auto-Deploy** to **After CI Checks Pass**
so a failing GitHub Actions run cannot be deployed automatically.

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

The public `/healthz/` endpoint returns only `{"status": "ok"}` when Django can
query the database and returns HTTP 503 otherwise. It is safe to use as the
Render web-service health-check path.

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
SENTRY_ENABLED=True
SENTRY_DSN=...
SENTRY_ENVIRONMENT=production
BACKUP_S3_ENDPOINT=https://s3.us-east-005.backblazeb2.com
BACKUP_S3_REGION=us-east-005
BACKUP_S3_BUCKET=overtone-backup-unique-suffix
BACKUP_S3_ACCESS_KEY_ID=...
BACKUP_S3_SECRET_ACCESS_KEY=...
BACKUP_S3_PREFIX=overtone
BACKUP_OBJECT_LOCK_DAYS=30
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
a real Resend API key, and real Supabase/S3-compatible storage credentials:

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

For error monitoring, create a Sentry Django project and set `SENTRY_DSN` in the
production environment. Sentry is disabled in debug mode by default. Production
events omit default PII, request bodies, local variables, query strings, user
context, sensitive headers, and UUID tokens embedded in URLs.

### Off-site backups and restore drills

Supabase Free does not provide automatic database backups, and a database dump
does not contain the actual objects stored through Supabase Storage. Overtone
therefore backs up both sources to a separate private Backblaze B2 bucket:

- `database.dump` is a PostgreSQL custom-format dump of the Django-owned
  `public` schema made with `pg_dump`. Supabase platform schemas and extensions
  are deliberately excluded so the dump restores into standard PostgreSQL.
- `media.tar.gz` contains every object in Django's configured private-media
  storage plus a per-object SHA-256 manifest.
- `manifest.json` is uploaded last and marks a backup as complete.
- every object requests AES-256 server-side encryption, 30-day governance-mode
  Object Lock, and is verified by stored size and SHA-256 metadata after upload.
- one backup is written under `overtone/daily/` each run. The first successful
  run in each calendar month also writes a copy under `overtone/monthly/`.

Use a bucket-specific B2 application key. It needs list, read, write, and file
retention permissions for this bucket, but it should not have account or key
administration permissions. Do not put client names, email addresses, or other
PII in bucket names or backup object keys. The bucket must use a lowercase
S3-compatible name. `BACKUP_S3_REGION` must be the full region token embedded in
the endpoint hostname, such as `us-east-005`, rather than the `US East` account
display label.

Configure these custom B2 lifecycle rules after Object Lock is enabled:

| Prefix | Hide after upload | Delete after hiding | Result |
|---|---:|---:|---|
| `overtone/daily/` | 31 days | 1 day | About 30 daily restore points |
| `overtone/monthly/` | 366 days | 1 day | About 12 monthly restore points |

Object Lock prevents a lifecycle rule from deleting a still-locked object. The
one-day margin means daily objects are not hidden until their 30-day lock has
expired.

Before changing the scheduled Render command, manually trigger and verify the
backup from the Render cron environment:

```bash
python manage.py backup_to_b2
python manage.py verify_backup
```

Both commands create `JobRun` history visible to a platform superuser. A backup
failure exits nonzero and therefore triggers Render's cron failure notification.
`BACKUP_DATABASE_URL` is optional; set it to a dedicated Supabase direct or
session-pooler connection if the normal application `DATABASE_URL` is unsuitable
for `pg_dump`.

Perform a restore drill at least quarterly. The restore command refuses to use
the configured application database, requires a separate `RESTORE_DATABASE_URL`,
and requires an explicit confirmation flag. The target database must already
exist and the media output directory must be empty:

```bash
createdb overtone_restore_drill
mkdir /tmp/overtone-restore-media
RESTORE_DATABASE_URL=postgresql:///overtone_restore_drill \
  python manage.py restore_backup \
  --confirm-isolated-target \
  --media-output-dir=/tmp/overtone-restore-media

DATABASE_URL=postgresql:///overtone_restore_drill DATABASE_SSL_REQUIRE=False \
  python manage.py check_tenant_integrity
DATABASE_URL=postgresql:///overtone_restore_drill DATABASE_SSL_REQUIRE=False \
  python manage.py check
```

Record the restore date, backup prefix, integrity result, media file count, and
any remediation. Only after the isolated database and media are validated should
they be promoted or copied into replacement production services.

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
- `Venue.organization` uses `SET_NULL`, so deleting an organization preserves its venues and clears their organization association.
- `ConditionReading.update_piano_current_state()` copies readings to denormalized fields on Piano for fast display.
- `Piano.advance_schedule(task_type, completed_date)` computes the next due date when a work order is completed.

---

## Supabase Public API Hardening

Supabase can expose tables in the `public` schema through its REST API if the
`anon` or `authenticated` database roles have grants. This Django app does not
use Supabase's client-side database API; it talks to Postgres from the server.

Migration `maintenance.0013_lock_down_supabase_public_api` enables row-level
security on public tables and revokes default table, sequence, and function
access from Supabase API roles. It is applied by the normal migration command:

```bash
python manage.py migrate
```

If you later add a deliberate Supabase REST/client feature, create narrow RLS
policies for only the specific tables and actions that feature needs.
