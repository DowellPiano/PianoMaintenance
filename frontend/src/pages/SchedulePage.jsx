import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import MonthCalendar from '../components/MonthCalendar'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import { apiFetch } from '../api'
import './SchedulePage.css'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function monthRange(year, month) {
  const start = `${year}-${String(month + 1).padStart(2, '0')}-01`
  const lastDay = new Date(year, month + 1, 0).getDate()
  const end = `${year}-${String(month + 1).padStart(2, '0')}-${lastDay}`
  return { start, end }
}

const STATUS_COLORS = {
  Open:          { bg: '#dbeafe', color: '#1d4ed8' },
  'In Progress': { bg: '#fef9c3', color: '#854d0e' },
  Complete:      { bg: '#d1fae5', color: '#065f46' },
  Cancelled:     { bg: '#f3f4f6', color: '#6b7280' },
  Upcoming:      { bg: '#ede9fe', color: '#5b21b6' },
  'Due Soon':    { bg: '#fef3c7', color: '#92400e' },
  Overdue:       { bg: '#fee2e2', color: '#991b1b' },
}

const PRIORITY_BADGE = {
  Urgent: { bg: '#fee2e2', color: '#991b1b', label: 'Urgent' },
  High:   { bg: '#ffedd5', color: '#9a3412', label: 'High'   },
  Normal: { bg: '#dbeafe', color: '#1e40af', label: 'Normal' },
  Low:    { bg: '#f3f4f6', color: '#6b7280', label: 'Low'    },
}

function StatusBadge({ status }) {
  const s = STATUS_COLORS[status] ?? STATUS_COLORS.Upcoming
  return <span className="badge" style={{ background: s.bg, color: s.color }}>{status}</span>
}

function PriorityBadge({ priority }) {
  if (!priority) return null
  const p = PRIORITY_BADGE[priority] ?? PRIORITY_BADGE.Normal
  return <span className="badge" style={{ background: p.bg, color: p.color }}>{p.label}</span>
}

// ─── Day Sidebar ──────────────────────────────────────────────────────────────

function DaySidebar({ date, events, onCreateWO, onEditWO, onClose }) {
  const navigate  = useNavigate()
  const dayEvents = events.filter(e => e.date === date)
  const fmt = date
    ? new Date(date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
    : ''

  return (
    <div className="day-sidebar">
      <div className="sidebar-header">
        <div>
          <h3>{fmt}</h3>
          <p className="sidebar-count">{dayEvents.length} event{dayEvents.length !== 1 ? 's' : ''}</p>
        </div>
        <button className="sidebar-close" onClick={onClose}>×</button>
      </div>

      <button className="btn-primary sidebar-add-btn" onClick={() => onCreateWO({ due_date: date })}>
        + New Work Order
      </button>

      {dayEvents.length === 0 ? (
        <p className="sidebar-empty">No events this day.</p>
      ) : (
        <div className="sidebar-events">
          {dayEvents.map(ev => (
            <div
              key={ev.id}
              className="sidebar-event-card"
              style={{ borderLeft: `4px solid ${ev.color}` }}
            >
              <div className="sev-top">
                <span className="sev-type">{ev.type === 'work_order' ? 'Work Order' : 'Schedule'}</span>
                <StatusBadge status={ev.status} />
              </div>
              <p className="sev-title">{ev.title}</p>
              {ev.piano_location && <p className="sev-meta">{ev.piano_location}</p>}
              {ev.description    && <p className="sev-desc">{ev.description}</p>}
              {ev.priority       && <PriorityBadge priority={ev.priority} />}
              {ev.assigned_tech  && <p className="sev-meta">{ev.assigned_tech}</p>}
              {ev.type === 'work_order' && (
                <div className="sev-actions">
                  <button className="sev-edit-btn" onClick={() => onEditWO(ev)}>Edit</button>
                  <button className="sev-edit-btn sev-goto-btn" onClick={() => navigate('/work-orders')}>
                    Go to Work Order →
                  </button>
                </div>
              )}
              {ev.type === 'schedule' && (
                <button className="sev-edit-btn" onClick={() => onCreateWO({
                  due_date: ev.date,
                  piano: String(ev.piano_id),
                  order_type: 'Preventive',
                  description: ev.description,
                }, ev)}>
                  Create Work Order
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Calendar View ────────────────────────────────────────────────────────────

function CalendarView({ onCreateWO, onEditWO }) {
  const todayDate = new Date()
  const [year,  setYear]  = useState(todayDate.getFullYear())
  const [month, setMonth] = useState(todayDate.getMonth())
  const [events,       setEvents]       = useState([])
  const [loading,      setLoading]      = useState(true)
  const [selectedDate, setSelectedDate] = useState(null)

  // Filter state
  const [typeFilter, setTypeFilter] = useState('both')  // 'both' | 'work_order' | 'schedule'
  const [locFilter,  setLocFilter]  = useState('')       // '' = all

  const loadEvents = useCallback(() => {
    setLoading(true)
    const { start, end } = monthRange(year, month)
    apiFetch(`/api/calendar-events/?start=${start}&end=${end}`)
      .then(r => r.json())
      .then(data => { setEvents(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [year, month])

  useEffect(() => { loadEvents() }, [loadEvents])

  function prevMonth() {
    if (month === 0) { setYear(y => y - 1); setMonth(11) }
    else setMonth(m => m - 1)
    setSelectedDate(null)
  }
  function nextMonth() {
    if (month === 11) { setYear(y => y + 1); setMonth(0) }
    else setMonth(m => m + 1)
    setSelectedDate(null)
  }
  function goToToday() {
    const now = new Date()
    setYear(now.getFullYear())
    setMonth(now.getMonth())
    setSelectedDate(null)
  }

  // Client-side filtering
  const locations = [...new Set(events.map(e => e.piano_location).filter(Boolean))].sort()
  const filtered = events.filter(e => {
    if (typeFilter !== 'both' && e.type !== typeFilter) return false
    if (locFilter && e.piano_location !== locFilter) return false
    return true
  })

  return (
    <div>
      {/* Filter bar */}
      <div className="cal-filter-bar">
        <div className="filter-group">
          {[
            { val: 'both',       label: 'Both' },
            { val: 'work_order', label: 'Work Orders' },
            { val: 'schedule',   label: 'Schedules' },
          ].map(({ val, label }) => (
            <button
              key={val}
              className={`filter-btn ${typeFilter === val ? 'active' : ''}`}
              onClick={() => setTypeFilter(val)}
            >{label}</button>
          ))}
        </div>
        <select
          className="loc-select"
          value={locFilter}
          onChange={e => setLocFilter(e.target.value)}
        >
          <option value="">All Locations</option>
          {locations.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>

      <div className={`cal-layout ${selectedDate ? 'with-sidebar' : ''}`}>
        <div className="cal-main">
          {loading && <div className="cal-loading">Loading…</div>}
          <MonthCalendar
            year={year} month={month} events={filtered}
            selectedDate={selectedDate}
            onPrev={prevMonth} onNext={nextMonth} onToday={goToToday}
            onSelectDate={d => setSelectedDate(d === selectedDate ? null : d)}
          />
        </div>

        {selectedDate && (
          <DaySidebar
            date={selectedDate}
            events={filtered}
            onCreateWO={(prefill, schedEv) => { onCreateWO(prefill, schedEv); setSelectedDate(null) }}
            onEditWO={ev => { onEditWO(ev); loadEvents() }}
            onClose={() => setSelectedDate(null)}
          />
        )}
      </div>
    </div>
  )
}

// ─── List View ────────────────────────────────────────────────────────────────

const TYPE_LABELS = { all: 'All', work_order: 'Work Orders', schedule: 'Schedules' }

function ListView({ onCreateWO, onEditWO }) {
  const today = new Date()
  const [events,      setEvents]      = useState([])
  const [loading,     setLoading]     = useState(true)
  const [typeFilter,  setTypeFilter]  = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    setLoading(true)
    const start = today.toISOString().slice(0, 10)
    const end90 = new Date(today); end90.setDate(today.getDate() + 90)
    const end = end90.toISOString().slice(0, 10)
    apiFetch(`/api/calendar-events/?start=${start}&end=${end}`)
      .then(r => r.json())
      .then(data => { setEvents(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = events.filter(e => {
    if (typeFilter !== 'all' && e.type !== typeFilter) return false
    if (statusFilter !== 'all' && e.status !== statusFilter) return false
    return true
  })

  const allStatuses = [...new Set(events.map(e => e.status))]

  return (
    <div>
      <div className="list-filters">
        <div className="filter-group">
          {Object.entries(TYPE_LABELS).map(([val, label]) => (
            <button
              key={val}
              className={`filter-btn ${typeFilter === val ? 'active' : ''}`}
              onClick={() => setTypeFilter(val)}
            >{label}</button>
          ))}
        </div>
        <div className="filter-group">
          <button
            className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >All Statuses</button>
          {allStatuses.map(s => (
            <button
              key={s}
              className={`filter-btn ${statusFilter === s ? 'active' : ''}`}
              onClick={() => setStatusFilter(s)}
            >{s}</button>
          ))}
        </div>
        <button className="btn-primary list-add-btn" onClick={() => onCreateWO({})}>
          + New Work Order
        </button>
      </div>

      {loading ? (
        <div className="td-loading" style={{ padding: '2rem 0' }}>
          <span className="td-loading-inner"><span className="spinner" />Loading events…</span>
        </div>
      ) : events.length === 0 ? (
        <div className="empty-state">
          <p>No scheduled events in the next 90 days.</p>
          <p className="meta">Work orders and active maintenance schedules will appear here once added.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <p>No events match the selected filters.</p>
          <button className="btn-secondary" style={{ marginTop: '0.75rem' }}
            onClick={() => { setTypeFilter('all'); setStatusFilter('all') }}>
            Clear filters
          </button>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Piano</th>
                <th>Location</th>
                <th>Task / Description</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(ev => (
                <tr key={ev.id}>
                  <td className="ev-date">{ev.date}</td>
                  <td>
                    <span className={`type-tag type-${ev.type}`}>
                      {ev.type === 'work_order' ? 'Work Order' : 'Schedule'}
                    </span>
                  </td>
                  <td className="fw-medium">{ev.piano_name}<br /><span className="meta">{ev.piano_brand}</span></td>
                  <td>{ev.piano_location}</td>
                  <td>{ev.description || ev.title}</td>
                  <td><StatusBadge status={ev.status} /></td>
                  <td>{ev.priority ? <PriorityBadge priority={ev.priority} /> : <span className="meta">—</span>}</td>
                  <td className="actions">
                    {ev.type === 'work_order' ? (
                      <button className="btn-edit" onClick={() => onEditWO(ev)}>Edit</button>
                    ) : (
                      <button className="btn-edit" onClick={() => onCreateWO({
                        due_date: ev.date,
                        piano: String(ev.piano_id),
                        order_type: 'Preventive',
                        description: ev.description,
                      }, ev)}>Create WO</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ─── Schedules View (Tasks 2 & 4) ─────────────────────────────────────────────

const SORT_OPTIONS = [
  { val: 'piano',     label: 'Piano' },
  { val: 'task_type', label: 'Task Type' },
  { val: 'next_due',  label: 'Next Due' },
]

function scheduleStatus(s) {
  if (s.is_paused)  return 'Paused'
  if (s.skip_next)  return 'Skip Pending'
  return 'Active'
}

const SCHED_STATUS_STYLE = {
  Active:        { bg: '#d1fae5', color: '#065f46' },
  Paused:        { bg: '#f3f4f6', color: '#6b7280' },
  'Skip Pending':{ bg: '#fef3c7', color: '#92400e' },
}

function SchedulesView() {
  const [schedules,   setSchedules]   = useState([])
  const [loading,     setLoading]     = useState(true)
  const [activeOnly,  setActiveOnly]  = useState(true)
  const [sortBy,      setSortBy]      = useState('next_due')
  const [skipConfirm, setSkipConfirm] = useState(null)  // schedule obj
  const [actionError, setActionError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    const params = activeOnly ? '?is_active=true' : ''
    apiFetch(`/api/schedules/${params}`)
      .then(r => r.json())
      .then(data => { setSchedules(data.results ?? data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [activeOnly])

  useEffect(() => { load() }, [load])

  async function togglePause(sched) {
    setActionError(null)
    const res = await apiFetch(`/api/schedules/${sched.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_paused: !sched.is_paused }),
    })
    if (res.ok) {
      const updated = await res.json()
      setSchedules(prev => prev.map(s => s.id === sched.id ? updated : s))
    } else {
      setActionError('Failed to update schedule.')
    }
  }

  async function confirmSkip(sched) {
    setActionError(null)
    const res = await apiFetch(`/api/schedules/${sched.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skip_next: true }),
    })
    if (res.ok) {
      const updated = await res.json()
      setSchedules(prev => prev.map(s => s.id === sched.id ? updated : s))
    } else {
      setActionError('Failed to set skip.')
    }
    setSkipConfirm(null)
  }

  // Sort
  const sorted = [...schedules].sort((a, b) => {
    if (sortBy === 'piano')     return (a.piano_name ?? '').localeCompare(b.piano_name ?? '')
    if (sortBy === 'task_type') return (a.task_type  ?? '').localeCompare(b.task_type  ?? '')
    if (sortBy === 'next_due')  return (a.next_due   ?? '').localeCompare(b.next_due   ?? '')
    return 0
  })

  return (
    <div>
      {/* Controls */}
      <div className="list-filters">
        <label className="active-only-toggle">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={e => setActiveOnly(e.target.checked)}
          />
          Active only
        </label>
        <div className="filter-group" style={{ marginLeft: 'auto' }}>
          <span className="sort-label">Sort:</span>
          {SORT_OPTIONS.map(({ val, label }) => (
            <button
              key={val}
              className={`filter-btn ${sortBy === val ? 'active' : ''}`}
              onClick={() => setSortBy(val)}
            >{label}</button>
          ))}
        </div>
      </div>

      {actionError && <div className="page-error" style={{ marginBottom: '0.75rem' }}>{actionError}</div>}

      {loading ? (
        <div className="td-loading" style={{ padding: '2rem 0' }}>
          <span className="td-loading-inner"><span className="spinner" />Loading schedules…</span>
        </div>
      ) : sorted.length === 0 ? (
        <div className="empty-state">
          <p>No maintenance schedules found.</p>
          <p className="meta">Add schedules from the Piano profile page.</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Piano</th>
                <th>Location</th>
                <th>Task</th>
                <th>Type</th>
                <th>Interval</th>
                <th>Next Due</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(s => {
                const status = scheduleStatus(s)
                const style  = SCHED_STATUS_STYLE[status]
                const muted  = s.is_paused
                return (
                  <tr key={s.id} className={muted ? 'row-paused' : ''}>
                    <td className="fw-medium" style={muted ? { opacity: 0.55 } : {}}>
                      {s.piano_name}
                    </td>
                    <td style={muted ? { opacity: 0.55 } : {}}>
                      {s.piano_location || <span className="meta">—</span>}
                    </td>
                    <td style={muted ? { opacity: 0.55 } : {}}>{s.task_name}</td>
                    <td style={muted ? { opacity: 0.55 } : {}}>{s.task_type}</td>
                    <td style={muted ? { opacity: 0.55 } : {}}>
                      Every {s.interval_days}d
                    </td>
                    <td style={muted ? { opacity: 0.55 } : {}}>
                      {s.next_due || <span className="meta">—</span>}
                    </td>
                    <td>
                      <span className="badge" style={{ background: style.bg, color: style.color }}>
                        {status}
                      </span>
                    </td>
                    <td className="actions">
                      <button
                        className={s.is_paused ? 'btn-resume' : 'btn-pause'}
                        onClick={() => togglePause(s)}
                      >
                        {s.is_paused ? 'Resume' : 'Pause'}
                      </button>
                      {!s.skip_next && !s.is_paused && (
                        <button
                          className="btn-skip"
                          onClick={() => setSkipConfirm(s)}
                        >
                          Skip Next
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Skip Next confirm dialog */}
      {skipConfirm && (
        <div className="modal-overlay" onClick={() => setSkipConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Skip Next Occurrence</h3>
            <p>
              Skip the next scheduled occurrence of <strong>{skipConfirm.task_name}</strong> for{' '}
              <strong>{skipConfirm.piano_name}</strong>?
              The following occurrence will proceed as normal.
            </p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setSkipConfirm(null)}>Cancel</button>
              <button className="btn-danger" onClick={() => confirmSkip(skipConfirm)}>Skip Next</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SchedulePage() {
  const [tab,       setTab]       = useState('calendar')
  const [woModal,   setWoModal]   = useState(false)
  const [editingWO, setEditingWO] = useState(null)
  const [prefillWO, setPrefillWO] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [sourceScheduleId, setSourceScheduleId] = useState(null)

  function openCreate(prefill = {}, schedEv = null) {
    setEditingWO(null)
    setPrefillWO(prefill)
    setSourceScheduleId(schedEv?.schedule_id ?? null)
    setWoModal(true)
  }

  function openEdit(ev) {
    if (ev.work_order_id) {
      apiFetch(`/api/work-orders/${ev.work_order_id}/`)
        .then(r => r.json())
        .then(wo => { setEditingWO(wo); setPrefillWO(null); setWoModal(true) })
    }
  }

  async function handleSaved() {
    setWoModal(false)
    if (sourceScheduleId) {
      await apiFetch(`/api/schedules/${sourceScheduleId}/`, { method: 'DELETE' })
      setSourceScheduleId(null)
    }
    setRefreshKey(k => k + 1)
  }

  return (
    <div className="schedule-page">
      <div className="page-header">
        <h2>Schedule</h2>
      </div>

      <div className="tabs">
        <button className={`tab-btn ${tab === 'calendar' ? 'active' : ''}`} onClick={() => setTab('calendar')}>
          Calendar
        </button>
        <button className={`tab-btn ${tab === 'list' ? 'active' : ''}`} onClick={() => setTab('list')}>
          List
        </button>
        <button className={`tab-btn ${tab === 'schedules' ? 'active' : ''}`} onClick={() => setTab('schedules')}>
          Schedules
        </button>
      </div>

      <div className="tab-content" key={refreshKey}>
        {tab === 'calendar'  && <CalendarView  onCreateWO={openCreate} onEditWO={openEdit} />}
        {tab === 'list'      && <ListView      onCreateWO={openCreate} onEditWO={openEdit} />}
        {tab === 'schedules' && <SchedulesView />}
      </div>

      {woModal && (
        <WorkOrderFormModal
          workOrder={editingWO}
          prefill={prefillWO}
          onClose={() => setWoModal(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
