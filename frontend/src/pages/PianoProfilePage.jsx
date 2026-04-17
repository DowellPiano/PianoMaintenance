import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import PianoFormModal from '../components/PianoFormModal'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import './PianoProfilePage.css'

// ─── Helpers ───────────────────────────────────────────────────────────────

function statusClass(s) {
  const map = {
    'Open': 'status-open',
    'In Progress': 'status-inprogress',
    'Complete': 'status-complete',
    'Cancelled': 'status-cancelled',
    'Overdue': 'status-overdue',
    'Due Soon': 'status-duesoon',
    'Upcoming': 'status-upcoming',
  }
  return map[s] ?? 'status-open'
}

function priorityClass(p) {
  const map = { 'Urgent': 'pri-urgent', 'High': 'pri-high', 'Normal': 'pri-normal', 'Low': 'pri-low' }
  return map[p] ?? ''
}

function typeClass(t) {
  const map = { 'Grand': 'type-grand', 'Upright': 'type-upright', 'Digital': 'type-digital' }
  return map[t] ?? ''
}

function fmt(val, fallback = '—') {
  return val || fallback
}

// ─── Tab: Details ──────────────────────────────────────────────────────────

function DetailsTab({ piano }) {
  const rows = [
    ['Brand', fmt(piano.brand)],
    ['Model', fmt(piano.model)],
    ['Piano Type', piano.piano_type],
    ['Serial Number', fmt(piano.serial_number)],
    ['Location', fmt(piano.location_name)],
    ['Date Acquired', fmt(piano.date_acquired)],
    ['QR Token', piano.qr_code_token],
    ['Notes', fmt(piano.notes)],
  ]

  return (
    <div className="details-grid">
      {rows.map(([label, value]) => (
        <div className="details-row" key={label}>
          <dt>{label}</dt>
          <dd className={value === '—' ? 'empty' : ''}>{value}</dd>
        </div>
      ))}
    </div>
  )
}

// ─── Tab: Photos ──────────────────────────────────────────────────────────

function PhotosTab({ pianoId, photos, onPhotosChanged }) {
  const [uploading, setUploading] = useState(false)
  const [caption, setCaption] = useState('')
  const [lightbox, setLightbox] = useState(null) // image_url string
  const [error, setError] = useState(null)
  const fileRef = useRef(null)

  async function handleUpload(e) {
    e.preventDefault()
    const file = fileRef.current?.files[0]
    if (!file) return
    setUploading(true)
    setError(null)
    const fd = new FormData()
    fd.append('piano', pianoId)
    fd.append('image', file)
    fd.append('caption', caption)
    try {
      const res = await fetch('/api/photos/', { method: 'POST', body: fd })
      if (!res.ok) {
        const d = await res.json()
        setError(JSON.stringify(d))
      } else {
        setCaption('')
        if (fileRef.current) fileRef.current.value = ''
        onPhotosChanged()
      }
    } catch {
      setError('Upload failed — is Django running?')
    } finally {
      setUploading(false)
    }
  }

  async function handleDelete(photo) {
    if (!window.confirm('Delete this photo?')) return
    await fetch(`/api/photos/${photo.id}/`, { method: 'DELETE' })
    onPhotosChanged()
  }

  async function handleSetProfile(photo) {
    await fetch(`/api/photos/${photo.id}/set_profile/`, { method: 'POST' })
    onPhotosChanged()
  }

  return (
    <div className="photos-tab">
      <form className="photo-upload-form" onSubmit={handleUpload}>
        <label className="upload-label">
          <span>Choose photo</span>
          <input type="file" ref={fileRef} accept="image/*" required />
        </label>
        <input
          type="text"
          placeholder="Caption (optional)"
          value={caption}
          onChange={e => setCaption(e.target.value)}
          className="caption-input"
        />
        <button type="submit" className="btn-primary" disabled={uploading}>
          {uploading ? 'Uploading…' : 'Upload Photo'}
        </button>
      </form>
      {error && <div className="tab-error">{error}</div>}

      {photos.length === 0 ? (
        <div className="empty-photos">No photos yet. Upload one above.</div>
      ) : (
        <div className="photo-grid">
          {photos.map(photo => (
            <div key={photo.id} className={`photo-card${photo.is_profile_photo ? ' photo-card--profile' : ''}`}>
              {photo.is_profile_photo && (
                <div className="profile-badge">Profile Photo</div>
              )}
              <img
                src={photo.image_url}
                alt={photo.caption || 'Piano photo'}
                className="photo-thumb"
                onClick={() => setLightbox(photo.image_url)}
              />
              {photo.caption && <p className="photo-caption">{photo.caption}</p>}
              <div className="photo-actions">
                {!photo.is_profile_photo && (
                  <button className="btn-sm btn-secondary" onClick={() => handleSetProfile(photo)}>
                    Set as Profile
                  </button>
                )}
                <button className="btn-sm btn-danger-sm" onClick={() => handleDelete(photo)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <div className="lightbox-inner" onClick={e => e.stopPropagation()}>
            <button className="lightbox-close" onClick={() => setLightbox(null)}>×</button>
            <img src={lightbox} alt="Full size" />
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Tab: Work History ────────────────────────────────────────────────────

function WorkHistoryTab({ workOrders, onWorkOrderSaved }) {
  const [editingWO, setEditingWO] = useState(null)

  return (
    <div className="work-history-tab">
      {workOrders.length === 0 ? (
        <div className="empty-tab">No work orders for this piano yet.</div>
      ) : (
        <div className="table-wrapper">
          <table className="profile-table">
            <thead>
              <tr>
                <th>WO #</th>
                <th>Date</th>
                <th>Type</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Assigned Tech</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {workOrders.map(wo => (
                <tr key={wo.id}>
                  <td className="wo-id">WO-{wo.id}</td>
                  <td>{wo.due_date || <span className="empty">—</span>}</td>
                  <td>{wo.order_type}</td>
                  <td>
                    <span className={`status-badge ${statusClass(wo.status)}`}>{wo.status}</span>
                  </td>
                  <td>
                    <span className={`priority-badge ${priorityClass(wo.priority)}`}>{wo.priority}</span>
                  </td>
                  <td>{wo.assigned_tech_name || <span className="empty">Unassigned</span>}</td>
                  <td className="desc-cell">{wo.description || <span className="empty">—</span>}</td>
                  <td>
                    <button className="btn-edit" onClick={() => setEditingWO(wo)}>Edit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editingWO && (
        <WorkOrderFormModal
          workOrder={editingWO}
          onClose={() => setEditingWO(null)}
          onSaved={() => { setEditingWO(null); onWorkOrderSaved() }}
        />
      )}
    </div>
  )
}

// ─── Tab: Upcoming Tasks ──────────────────────────────────────────────────

function UpcomingTasksTab({ pianoId }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const today = new Date()
    const start = today.toISOString().slice(0, 10)
    const endDate = new Date(today)
    endDate.setDate(endDate.getDate() + 90)
    const end = endDate.toISOString().slice(0, 10)

    fetch(`/api/calendar-events/?start=${start}&end=${end}`)
      .then(r => r.json())
      .then(data => {
        const filtered = data.filter(ev => String(ev.piano_id) === String(pianoId))
        setEvents(filtered)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [pianoId])

  if (loading) return <div className="loading">Loading…</div>

  return (
    <div className="upcoming-tasks-tab">
      {events.length === 0 ? (
        <div className="empty-tab">No upcoming tasks in the next 90 days.</div>
      ) : (
        <div className="table-wrapper">
          <table className="profile-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>Task</th>
                <th>Status</th>
                <th>Priority</th>
              </tr>
            </thead>
            <tbody>
              {events.map(ev => (
                <tr key={ev.id}>
                  <td>{ev.date}</td>
                  <td>
                    <span className={`event-type-badge event-type-${ev.type}`}>
                      {ev.type === 'work_order' ? 'Work Order' : 'Schedule'}
                    </span>
                  </td>
                  <td>{ev.description || ev.title}</td>
                  <td>
                    <span className={`status-badge ${statusClass(ev.status)}`}>{ev.status}</span>
                  </td>
                  <td>
                    {ev.priority
                      ? <span className={`priority-badge ${priorityClass(ev.priority)}`}>{ev.priority}</span>
                      : <span className="empty">—</span>
                    }
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

// ─── Tab: Active Schedules ────────────────────────────────────────────────

function SchedulesTab({ schedules }) {
  return (
    <div className="schedules-tab">
      {schedules.length === 0 ? (
        <div className="empty-tab">No active maintenance schedules for this piano.</div>
      ) : (
        <div className="table-wrapper">
          <table className="profile-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Type</th>
                <th>Every (days)</th>
                <th>Warning (days)</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {schedules.map(s => (
                <tr key={s.id}>
                  <td>{s.task_name}</td>
                  <td>{s.task_type}</td>
                  <td>{s.interval_days}</td>
                  <td>{s.warning_days_before}</td>
                  <td>
                    {s.template_name
                      ? <span className="source-template">Template: {s.template_name}</span>
                      : <span className="source-manual">Manual</span>
                    }
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

// ─── Main Page ────────────────────────────────────────────────────────────

const TABS = ['Details', 'Photos', 'Work History', 'Upcoming Tasks', 'Schedules']

export default function PianoProfilePage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [profile, setProfile] = useState(null)   // { piano, work_orders, schedules, photos }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('Details')
  const [editModalOpen, setEditModalOpen] = useState(false)

  const loadProfile = useCallback(() => {
    setLoading(true)
    fetch(`/api/pianos/${id}/profile/`)
      .then(r => {
        if (!r.ok) throw new Error('Not found')
        return r.json()
      })
      .then(data => { setProfile(data); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [id])

  useEffect(() => { loadProfile() }, [loadProfile])

  if (loading) return <div className="profile-loading"><div className="spinner" />Loading piano profile…</div>
  if (error) return <div className="profile-error">Error: {error}</div>

  const { piano, work_orders, schedules, photos } = profile

  const openWOs  = work_orders.filter(wo => wo.status === 'Open' || wo.status === 'In Progress').length
  const doneWOs  = work_orders.filter(wo => wo.status === 'Complete').length

  return (
    <div className="profile-page">
      {/* ── Back nav ── */}
      <button className="back-btn" onClick={() => navigate('/pianos')}>
        ← Back to Pianos
      </button>

      {/* ── Hero header ── */}
      <div className="profile-hero">
        <div className="hero-photo-wrap">
          {piano.profile_photo_url ? (
            <img src={piano.profile_photo_url} alt={piano.name} className="hero-photo" />
          ) : (
            <div className="hero-photo hero-photo-placeholder">🎹</div>
          )}
        </div>

        <div className="hero-info">
          <div className="hero-name-row">
            <h2 className="hero-name">{piano.name}</h2>
            <span className={`badge ${typeClass(piano.piano_type)}`}>{piano.piano_type}</span>
          </div>
          <p className="hero-sub">{piano.brand}{piano.model ? ` — ${piano.model}` : ''}</p>
          <p className="hero-location">
            <span className="location-icon">📍</span> {piano.location_name}
          </p>

          <div className="hero-stats">
            <div className="stat-pill">
              <span className="stat-num">{work_orders.length}</span>
              <span className="stat-label">Total WOs</span>
            </div>
            <div className="stat-pill stat-pill--active">
              <span className="stat-num">{openWOs}</span>
              <span className="stat-label">Open</span>
            </div>
            <div className="stat-pill stat-pill--done">
              <span className="stat-num">{doneWOs}</span>
              <span className="stat-label">Complete</span>
            </div>
            <div className="stat-pill">
              <span className="stat-num">{schedules.length}</span>
              <span className="stat-label">Schedules</span>
            </div>
            <div className="stat-pill">
              <span className="stat-num">{photos.length}</span>
              <span className="stat-label">Photos</span>
            </div>
          </div>
        </div>

        <button className="hero-edit-btn" onClick={() => setEditModalOpen(true)}>
          Edit Piano
        </button>
      </div>

      {/* ── Tabs ── */}
      <div className="profile-tabs">
        {TABS.map(tab => (
          <button
            key={tab}
            className={`tab-btn${activeTab === tab ? ' tab-btn--active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
            {tab === 'Work History' && work_orders.length > 0 && (
              <span className="tab-count">{work_orders.length}</span>
            )}
            {tab === 'Photos' && photos.length > 0 && (
              <span className="tab-count">{photos.length}</span>
            )}
            {tab === 'Schedules' && schedules.length > 0 && (
              <span className="tab-count">{schedules.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Tab content ── */}
      <div className="profile-tab-content">
        {activeTab === 'Details' && <DetailsTab piano={piano} />}
        {activeTab === 'Photos' && (
          <PhotosTab
            pianoId={id}
            photos={photos}
            onPhotosChanged={loadProfile}
          />
        )}
        {activeTab === 'Work History' && (
          <WorkHistoryTab
            workOrders={work_orders}
            onWorkOrderSaved={loadProfile}
          />
        )}
        {activeTab === 'Upcoming Tasks' && <UpcomingTasksTab pianoId={id} />}
        {activeTab === 'Schedules' && <SchedulesTab schedules={schedules} />}
      </div>

      {/* ── Edit Piano modal ── */}
      {editModalOpen && (
        <PianoFormModal
          piano={piano}
          onClose={() => setEditModalOpen(false)}
          onSaved={() => { setEditModalOpen(false); loadProfile() }}
        />
      )}
    </div>
  )
}
