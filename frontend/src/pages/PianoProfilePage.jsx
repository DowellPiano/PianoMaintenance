import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import StartWorkOrderModal from '../components/StartWorkOrderModal'
import CompleteWorkOrderModal from '../components/CompleteWorkOrderModal'
import './PianoProfilePage.css'

// ─── Date helpers ─────────────────────────────────────────────────────────────

function today() {
  return new Date().toISOString().slice(0, 10)
}

function addDays(dateStr, days) {
  const d = new Date(dateStr)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

function calcNextDue(schedule) {
  // If never serviced, treat today as the base (immediately due)
  const base = schedule.last_service_date ?? today()
  return addDays(base, schedule.interval_days)
}

function scheduleStatus(schedule) {
  const nextDue = calcNextDue(schedule)
  const now     = today()
  const warnBy  = addDays(nextDue, -schedule.warning_days_before)
  if (nextDue < now)     return 'overdue'
  if (now >= warnBy)     return 'due-soon'
  return 'on-track'
}

const STATUS_LABELS = {
  'overdue':  'Overdue',
  'due-soon': 'Due Soon',
  'on-track': 'On Track',
}

// ─── Piano Info Card ──────────────────────────────────────────────────────────

function PianoCard({ piano }) {
  return (
    <div className="pp-card">
      <div className="pp-card-row">
        <div className="pp-field"><span className="pp-label">Brand</span><span>{piano.brand}</span></div>
        <div className="pp-field"><span className="pp-label">Model</span><span>{piano.model || '—'}</span></div>
        <div className="pp-field"><span className="pp-label">Type</span>
          <span className={`badge type-${piano.piano_type?.toLowerCase()}`}>{piano.piano_type}</span>
        </div>
      </div>
      <div className="pp-card-row">
        <div className="pp-field"><span className="pp-label">Location</span><span>{piano.location_name}</span></div>
        <div className="pp-field"><span className="pp-label">Serial #</span><span>{piano.serial_number || '—'}</span></div>
        <div className="pp-field"><span className="pp-label">Acquired</span><span>{piano.date_acquired || '—'}</span></div>
      </div>
      {piano.notes && (
        <div className="pp-notes"><span className="pp-label">Notes</span><p>{piano.notes}</p></div>
      )}
    </div>
  )
}

// ─── Upcoming Tasks ───────────────────────────────────────────────────────────

function UpcomingTasks({ piano, schedules, onWorkOrderStarted }) {
  const [startModal, setStartModal] = useState(null) // schedule or null

  const active = schedules.filter(s => s.is_active)

  if (active.length === 0) {
    return (
      <div className="pp-section">
        <h3 className="pp-section-title">Upcoming Tasks</h3>
        <p className="pp-empty">No active maintenance schedules. Add schedules via the Maintenance page.</p>
      </div>
    )
  }

  return (
    <div className="pp-section">
      <h3 className="pp-section-title">Upcoming Tasks</h3>
      <div className="table-wrapper">
        <table className="pp-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Type</th>
              <th>Interval</th>
              <th>Last Service</th>
              <th>Next Due</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {active.map(s => {
              const status  = scheduleStatus(s)
              const nextDue = calcNextDue(s)
              return (
                <tr key={s.id}>
                  <td className="fw-medium">{s.task_name}</td>
                  <td><span className="badge task-type">{s.task_type}</span></td>
                  <td>Every {s.interval_days}d</td>
                  <td>{s.last_service_date || <span className="pp-dim">Never</span>}</td>
                  <td>{nextDue}</td>
                  <td><span className={`badge status-${status}`}>{STATUS_LABELS[status]}</span></td>
                  <td>
                    <button
                      className="btn-start-wo"
                      onClick={() => setStartModal(s)}
                    >
                      Start Work Order
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {startModal && (
        <StartWorkOrderModal
          piano={piano}
          schedule={startModal}
          onClose={() => setStartModal(null)}
          onSaved={() => { setStartModal(null); onWorkOrderStarted() }}
        />
      )}
    </div>
  )
}

// ─── Open Work Orders ─────────────────────────────────────────────────────────

const EDITABLE_STATUSES = ['Open', 'In Progress', 'Cancelled']

function OpenWorkOrders({ piano, workOrders, onChanged }) {
  const [completeModal, setCompleteModal] = useState(null)
  const [editStatus,    setEditStatus]    = useState({}) // id → value
  const [error,         setError]         = useState(null)

  const open = workOrders.filter(wo => wo.status === 'Open' || wo.status === 'In Progress')

  async function handleStatusChange(wo, newStatus) {
    setEditStatus(s => ({ ...s, [wo.id]: newStatus }))
    const r = await fetch(`/api/work-orders/${wo.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    })
    if (!r.ok) { setError('Status update failed.'); return }
    onChanged()
  }

  if (open.length === 0) {
    return (
      <div className="pp-section">
        <h3 className="pp-section-title">Open Work Orders</h3>
        <p className="pp-empty">No open work orders for this piano.</p>
      </div>
    )
  }

  return (
    <div className="pp-section">
      <h3 className="pp-section-title">Open Work Orders</h3>
      {error && <div className="pp-error">{error}</div>}
      <div className="table-wrapper">
        <table className="pp-table">
          <thead>
            <tr>
              <th>WO #</th>
              <th>Type</th>
              <th>Priority</th>
              <th>Description</th>
              <th>Status</th>
              <th>Due Date</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {open.map(wo => (
              <tr key={wo.id}>
                <td className="fw-medium">#{wo.id}</td>
                <td>{wo.order_type}</td>
                <td><span className={`badge priority-${wo.priority?.toLowerCase()}`}>{wo.priority}</span></td>
                <td className="pp-desc">{wo.description || <span className="pp-dim">—</span>}</td>
                <td>
                  <select
                    value={editStatus[wo.id] ?? wo.status}
                    onChange={e => handleStatusChange(wo, e.target.value)}
                    className="pp-status-select"
                  >
                    {EDITABLE_STATUSES.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </td>
                <td>{wo.due_date || <span className="pp-dim">—</span>}</td>
                <td>
                  <button
                    className="btn-complete-wo"
                    onClick={() => setCompleteModal(wo)}
                  >
                    Complete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {completeModal && (
        <CompleteWorkOrderModal
          workOrder={completeModal}
          onClose={() => setCompleteModal(null)}
          onCompleted={() => { setCompleteModal(null); onChanged() }}
        />
      )}
    </div>
  )
}

// ─── Attachments ──────────────────────────────────────────────────────────────

function Attachments({ pianoId }) {
  const [attachments,    setAttachments]    = useState([])
  const [uploading,      setUploading]      = useState(false)
  const [error,          setError]          = useState(null)
  const [deleteConfirm,  setDeleteConfirm]  = useState(null)

  const loadAttachments = useCallback(() => {
    fetch(`/api/attachments/?piano=${pianoId}`)
      .then(r => r.json())
      .then(d => setAttachments(d.results ?? d))
      .catch(() => setError('Failed to load attachments.'))
  }, [pianoId])

  useEffect(() => { loadAttachments() }, [loadAttachments])

  async function handleFileUpload(e) {
    const files = Array.from(e.target.files)
    if (!files.length) return
    setUploading(true)
    setError(null)
    try {
      const formData = new FormData()
      files.forEach(f => formData.append('file', f))
      formData.append('piano', pianoId)
      const r = await fetch('/api/attachments/', { method: 'POST', body: formData })
      if (!r.ok) { setError('Upload failed.'); return }
      loadAttachments()
    } catch {
      setError('Upload failed — network error.')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function handleDelete(att) {
    const r = await fetch(`/api/attachments/${att.id}/`, { method: 'DELETE' })
    if (!r.ok) { setError('Delete failed.'); return }
    setDeleteConfirm(null)
    loadAttachments()
  }

  return (
    <div className="pp-section">
      <div className="pp-section-header">
        <h3 className="pp-section-title">Attachments</h3>
        <label className="btn-upload">
          {uploading ? 'Uploading…' : '+ Upload Files'}
          <input
            type="file"
            multiple
            onChange={handleFileUpload}
            accept="image/*,application/pdf,.doc,.docx"
            style={{ display: 'none' }}
            disabled={uploading}
          />
        </label>
      </div>

      {error && <div className="pp-error">{error}</div>}

      {attachments.length === 0 ? (
        <p className="pp-empty">No attachments yet. Upload photos, PDFs, or documents.</p>
      ) : (
        <ul className="pp-attachment-list">
          {attachments.map(att => (
            <li key={att.id} className="pp-attachment-row">
              <a href={att.file_url ?? att.file} target="_blank" rel="noreferrer" className="pp-attachment-link">
                📎 {att.filename ?? att.original_name ?? att.file?.split('/').pop() ?? `Attachment ${att.id}`}
              </a>
              <span className="pp-dim pp-att-date">{att.uploaded_at?.slice(0, 10) ?? ''}</span>
              <button className="btn-delete-sm" onClick={() => setDeleteConfirm(att)}>Delete</button>
            </li>
          ))}
        </ul>
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Attachment</h3>
            <p>Delete <strong>{deleteConfirm.filename ?? `Attachment ${deleteConfirm.id}`}</strong>? This cannot be undone.</p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(null)}>Cancel</button>
              <button className="btn-danger"    onClick={() => handleDelete(deleteConfirm)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PianoProfilePage() {
  const { id } = useParams()

  const [piano,     setPiano]     = useState(null)
  const [schedules, setSchedules] = useState([])
  const [workOrders,setWorkOrders]= useState([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)

  const loadSchedules = useCallback(() => {
    // NOTE for backend engineer: GET /api/schedules/?piano=<id> requires a piano filter param
    fetch(`/api/schedules/?piano=${id}`)
      .then(r => r.json())
      .then(d => setSchedules(d.results ?? d))
      .catch(() => {})
  }, [id])

  const loadWorkOrders = useCallback(() => {
    fetch(`/api/work-orders/?piano=${id}`)
      .then(r => r.json())
      .then(d => setWorkOrders(d.results ?? d))
      .catch(() => {})
  }, [id])

  useEffect(() => {
    setLoading(true)
    fetch(`/api/pianos/${id}/`)
      .then(r => {
        if (!r.ok) throw new Error('Not found')
        return r.json()
      })
      .then(data => { setPiano(data); setLoading(false) })
      .catch(() => { setError('Piano not found.'); setLoading(false) })

    loadSchedules()
    loadWorkOrders()
  }, [id, loadSchedules, loadWorkOrders])

  if (loading) return <div className="pp-page"><div className="loading">Loading…</div></div>
  if (error)   return (
    <div className="pp-page">
      <div className="pp-error">{error}</div>
      <Link to="/pianos" className="pp-back">← Back to Pianos</Link>
    </div>
  )
  if (!piano)  return null

  return (
    <div className="pp-page">
      <div className="pp-breadcrumb">
        <Link to="/pianos" className="pp-back">← Back to Pianos</Link>
      </div>

      <div className="page-header">
        <div>
          <h2>{piano.name}</h2>
          <p className="page-subtitle">{piano.brand} {piano.model} · {piano.location_name}</p>
        </div>
      </div>

      <PianoCard piano={piano} />
      <UpcomingTasks
        piano={piano}
        schedules={schedules}
        onWorkOrderStarted={loadWorkOrders}
      />
      <OpenWorkOrders
        piano={piano}
        workOrders={workOrders}
        onChanged={loadWorkOrders}
      />
      <Attachments pianoId={id} />
    </div>
  )
}
