# Application Performance Plan

This file tracks measured performance findings, implementation decisions, and
verification results. The goal is to reduce latency, database load, response
size, and browser work without increasing the application's CPU or RAM
allocation.

## Measurement notes

- Baseline captured 2026-09-07 using Django's test client and query capture.
- The synthetic data set used SQLite with 200 pianos, 1,000 open work orders,
  50 maintenance logs with two parts each, and 300 maintenance requests.
- Local timings are directional rather than production latency targets. Query
  counts and response-size growth are the primary signals; production changes
  should also be checked against Sentry transaction data and PostgreSQL
  `EXPLAIN ANALYZE` output.

## Baseline

| Path or operation | Queries | Local time | Response size | Finding |
| --- | ---: | ---: | ---: | --- |
| Dashboard, admin | 15 | 36.5 ms | 18 KB | Work-order counts are already combined. |
| Piano list, 25 rows | 10 | 10.9 ms | 29 KB | Paginated; browser image work is not included. |
| Work-order list, 50 rows | 8 | 19.3 ms | 86 KB | Paginated; technician options repeat per row. |
| Schedule, 1,000 open orders | 6 | 93.0 ms | 456 KB | Constant queries but unbounded rendering. |
| Technician dashboard, 1,000 assigned orders | 8 | 117.9 ms | 441 KB | Unbounded rendering. |
| Request list, 300 requests | 4 | 43.2 ms | 432 KB | Unbounded rendering. |
| Work-order detail, 50 logs and 100 part usages | 161 | 36.4 ms | 36 KB | N+1 queries for part usages and parts. |
| Scheduled generation, 200 pianos, dry run | 1,802 | 472.7 ms | n/a | Queries occur inside nested piano/task loops. |

## Work plan

### P0 — Remove work-order history N+1 queries

- Status: implemented 2026-09-07.
- Change: prefetch each log's part usages with its related part in one query.
- Verified result: the log/part portion dropped from 151 queries to 2. The full
  synthetic detail page, including the membership-query improvement below,
  dropped from 161 queries to 13 (about 92% fewer) with the same 50 logs and
  100 part usages.
- Guardrail: a performance regression test renders 20 logs and 40 usages,
  asserts one part-usage query with the part join, and caps total page queries.

### P0 — Bound large interactive pages

- Status: implemented 2026-09-07.
- Completed: capped the technician dashboard at 10 actionable work orders,
  matching the admin dashboard.
- Completed: paginated maintenance requests at 50 rows while preserving the
  active status filter in pagination links.
- Verified: with the synthetic data set, the technician dashboard fell from
  441 KB to 13 KB and from 117.9 ms to 31.7 ms. The request list fell from
  432 KB to 79 KB and from 43.2 ms to 11.8 ms.
- Completed: paginated the four-column schedule at 100 work orders per page;
  filters remain in pagination links and the paginator retains the accurate
  total result count.
- Verified: the 1,000-order schedule response fell from 456 KB to 59 KB and
  from 93.0 ms to a 13.5 ms warmed median.

### P0 — Optimize piano-card photos

- Status: partially implemented 2026-09-07.
- Completed: new uploads generate a maximum 640 by 480 JPEG derivative before
  the original is sent to storage; piano cards request the derivative and fall
  back to the original for existing photos.
- Completed: added lazy loading, asynchronous decoding, and explicit dimensions
  to piano-card images.
- Completed: canonical dated image and thumbnail paths bypass storage existence
  requests. Legacy paths retain the compatibility lookup.
- Completed: added a streaming `backfill_photo_thumbnails` command with company,
  limit, and dry-run controls for existing photos.
- Remaining: run the backfill in production, then consider removing the legacy
  storage-name fallback after confirming no legacy rows remain.
- Preserve authenticated access and short-lived signed URLs.

### P1 — Batch scheduled work-order generation

- Status: implemented 2026-09-07.
- Completed: latest completed service dates and existing open-order keys are
  fetched in grouped queries instead of querying per piano and task type.
- Completed: valid due-date updates and new work orders are written in bounded
  batches.
- Verified: the 200-piano dry-run benchmark dropped from 1,802 queries and
  472.7 ms to 4 queries and a 5.8 ms warmed median.
- Guardrail: a dry-run regression test covers 26 pianos and 25 custom schedules
  with no more than five queries while preserving duplicate prevention.

### P1 — Add targeted composite indexes

- Status: implemented locally 2026-09-07; production plans should be checked
  after deployment.
- Added indexes for the measured access patterns:
  - work orders by company and creation date;
  - schedule rows by company and due-date display order;
  - service history by piano, task type, status, and completion date;
  - requests by company and creation date;
  - audit events by company, target model, target id, and creation date.
- SQLite plan verification confirms all five access patterns select their new
  indexes without temporary sorting. Recheck the indexes with PostgreSQL
  `EXPLAIN ANALYZE` and remove any that production does not use.

### P1 — Remove repeated request work

- Status: implemented 2026-09-07.
- Completed: work-order authorization now reuses the active membership already
  loaded by middleware instead of querying membership again in each permission
  helper.
- Completed: work-order assignment selectors now load on demand, so list and
  detail pages do not repeat or fetch the complete technician roster until an
  admin chooses to change an assignment.

### P2 — Organize hot-path query logic

- Status: planned.
- Split the large view module by feature only after the measured hot-path fixes
  are stable. Moving code between files is not itself a runtime optimization.
- Centralize reusable list/detail query shapes in custom QuerySet methods or a
  small query module so required `select_related` and `prefetch_related` calls
  are difficult to omit.
- Keep performance regression tests beside the behavior they protect.

## Existing strengths to preserve

- Piano and work-order lists are paginated.
- Primary list pages already use `select_related` and targeted prefetching.
- Dashboard work-order counts use one aggregate query.
- Authenticated requests resolve active memberships once in middleware.
- Production database connections are persistent and static assets use
  compressed manifest storage.
- Existing performance regression tests cover piano lists, work-order lists,
  dashboard counts, schedule query count, and platform summary queries.

## Change log

### 2026-09-07

- Established the synthetic baseline above.
- Added this performance plan and change log.
- Prefetched work-order log part usages and their parts.
- Added regression coverage for work-order-detail query growth.
- Capped the technician dashboard at 10 work orders and added a regression
  test for the limit.
- Paginated maintenance requests at 50 rows and added pagination/query-count
  regression coverage.
- Reused the request's active membership in work-order permission checks,
  removing two database queries from work-order detail requests.
- Verified the initial set of changes against all 192 tests with the documented
  local-storage test environment.
- Paginated the schedule at 100 work orders per page and expanded its fixed
  query-count regression coverage to verify both pages.
- Added upload-time piano-card thumbnails, lazy image decoding, canonical-path
  storage probe avoidance, thumbnail cleanup, and photo regression coverage.
- Added a bounded-memory command to backfill thumbnails for existing photos.
- Batched scheduled work-order reads and writes and added a constant-query
  regression test covering built-in and custom schedules.
- Changed work-order assignment controls to load technician options on demand,
  removing one list/detail query and repeated option markup.
- Added targeted composite indexes for work-order recency, active due dates,
  service history, request recency, and target-specific audit history.
- Replaced the conditional schedule index after SQLite plan inspection showed
  it was not selected; the replacement serves the actual due-date sort without
  a temporary B-tree.
- Verified the completed change set against all 197 application tests.

## Deployment state

- Migrations `0020_photo_thumbnail` and `0021_performance_indexes` were applied
  to the configured Supabase database during schema validation on 2026-09-07.
- Migration `0022_replace_active_due_index` remains pending there and should be
  applied through the normal deployment workflow.
- The thumbnail backfill has not been run; existing photos will continue to
  fall back to their original image until it is scheduled explicitly.
