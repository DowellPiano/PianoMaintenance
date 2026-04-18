import { useState, useEffect, useCallback } from 'react'
import MonthCalendar from '../components/MonthCalendar'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import './SchedulePage.css'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function monthRange(year, month) {
  const start = `${year}-${String(month + 1).padStart(2, '0')}-01`
  const lastDay = new Date(year, month + 1, 0).getDate()
  const end = `${year}-${String(month + 1).padStart(2, '0')}-${lastDay}`
  return { start, end }
}

const STATUS_COLORS = {
  Open:        { bg: '#dbeafe', color: '#1d4ed8' },
  'In Progress':{ bg: '#fef9c3', color: '#854d0e' },
  Complete:    { bg: '#d1fae5', color: '#065f46' },
  Cancelled:   { bg: '#f3f4f6', color: '#6b7280' },
  Upcoming:    { bg: '#ede9fe', color: '#5b21b6' },
  'Due Soon':  { bg: '#fef3c7', color: '#92400e' },
  Overdue:     { bg: '#fee2e2', color: '#991b1b' },
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
                <span className="sev-type">{ev.type === 'work_order' ? '🔧 Work Order' : '📅 Schedule'}</span>
                <StatusBadge status={ev.status} />
              </div>
              <p className="sev-title">{ev.title}</p>
              {ev.piano_location && <p className="sev-meta">{ev.piano_location}</p>}
              {ev.description    && <p className="sev-desc">{ev.description}</p>}
              {ev.priority       && <PriorityBadge priority={ev.priority} />}
              {ev.assigned_tech  && <p className="sev-meta">👤 {ev.assigned_tech}</p>}
              {ev.type === 'work_order' && (
                <button className="sev-edit-btn" onClick={() => onEditWO(ev)}>Edit</button>
              )}
              {ev.type === 'schedule' && (
                <button className="sev-edit-btn" onClick={() => onCreateWO({
                  due_date: ev.date,
                  piano: String(ev.piano_id),
                  order_type: 'Preventive',
                  description: ev.description,
                })}>
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
  const today = new Date()
  const [year,  setYear]  = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [events,       setEvents]       = useState([])
  const [loading,      setLoading]      = useState(true)
  const [selectedDate, setSelectedDate] = useState(null)

  const loadEvents = useCallback(() => {
    setLoading(true)
    const { start, end } = monthRange(year, month)
    fetch(`/api/calendar-events/?start=${start}&end=${end}`)
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

  return (
    <div className={`cal-layout ${selectedDate ? 'with-sidebar' : ''}`}>
      <div className="cal-main">
        {loading && <div className="cal-loading">Loading…</div>}
        <MonthCalendar
          year={year} month={month} events={events}
          selectedDate={selectedDate}
          onPrev={prevMonth} onNext={nextMonth}
          onSelectDate={d => setSelectedDate(d === selectedDate ? null : d)}
        />
      </div>

      {selectedDate && (
        <DaySidebar
          date={selectedDate}
          events={events}
          onCreateWO={prefill => { onCreateWO(prefill); setSelectedDate(null) }}
          onEditWO={ev => { onEditWO(ev); loadEvents() }}
          onClose={() => setSelectedDate(null)}
        />
      )}
    </div>
  )
}

// ─── List View ────────────────────────────────────────────────────────────────

const TYPE_LABELS = { all: 'All', work_order: 'Work Orders', schedule: 'Schedules' }

function ListView({ onCreateWO, onEditWO }) {
  const today = new Date()
  const [events,    setEvents]    = useState([])
  const [loading,   setLoading]   = useState(true)
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    setLoading(true)
    // Load next 90 days
    const start = today.toISOString().slice(0, 10)
    const end90 = new Date(today); end90.setDate(today.getDate() + 90)
    const end = end90.toISOString().slice(0, 10)
    fetch(`/api/calendar-events/?start=${start}&end=${end}`)
      .then(r => r.json())
      .then(data => { setEvents(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const filtered = events.filter(e => {
    if (typeFilter !== 'all' && e.type !== typeFilter) return false
    if (statusFilter !== 'all' && e.status !== statusFilter) return false
    return true
  })

  const allStatuses = [...new Set(events.map(e => e.status))]

  return (
    <div>
      {/* Filters */}
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
        <div className="loading">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="empty-state"><p>No events in the next 90 days.</p></div>
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
                      {ev.type === 'work_order' ? '🔧 Work Order' : '📅 Schedule'}
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
                      })}>Create WO</button>
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

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SchedulePage() {
  const [tab,       setTab]       = useState('calendar')
  const [woModal,   setWoModal]   = useState(false)
  const [editingWO, setEditingWO] = useState(null)
  const [prefillWO, setPrefillWO] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  function openCreate(prefill = {}) {
    setEditingWO(null)
    setPrefillWO(prefill)
    setWoModal(true)
  }

  function openEdit(ev) {
    // ev is a calendar event shape; fetch the real WO from API
    if (ev.work_order_id) {
      fetch(`/api/work-orders/${ev.work_order_id}/`)
        .then(r => r.json())
        .then(wo => { setEditingWO(wo); setPrefillWO(null); setWoModal(true) })
    }
  }

  function handleSaved() {
    setWoModal(false)
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
      </div>

      <div className="tab-content" key={refreshKey}>
        {tab === 'calendar'
          ? <CalendarView onCreateWO={openCreate} onEditWO={openEdit} />
          : <ListView    onCreateWO={openCreate} onEditWO={openEdit} />
        }
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
