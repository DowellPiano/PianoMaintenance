import { useState, useEffect, useCallback } from 'react'
import ScheduleFormModal from '../components/ScheduleFormModal'
import TemplateFormModal from '../components/TemplateFormModal'
import ApplyTemplateModal from '../components/ApplyTemplateModal'
import './MaintenancePage.css'

const TASK_TYPE_COLORS = {
  Tuning:     { bg: '#ede9fe', color: '#5b21b6' },
  Regulation: { bg: '#dbeafe', color: '#1e40af' },
  Voicing:    { bg: '#fef9c3', color: '#854d0e' },
  Cleaning:   { bg: '#d1fae5', color: '#065f46' },
  Inspection: { bg: '#ffe4e6', color: '#9f1239' },
  Other:      { bg: '#f3f4f6', color: '#374151' },
}

function TaskBadge({ type }) {
  const style = TASK_TYPE_COLORS[type] ?? TASK_TYPE_COLORS.Other
  return (
    <span className="badge" style={{ background: style.bg, color: style.color }}>
      {type}
    </span>
  )
}

// ─── Schedules Tab ──────────────────────────────────────────────────────────

function SchedulesTab() {
  const [schedules, setSchedules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/schedules/')
      .then(r => r.json())
      .then(data => { setSchedules(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load schedules.'); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  async function handleDelete(s) {
    await fetch(`/api/schedules/${s.id}/`, { method: 'DELETE' })
    setDeleteConfirm(null)
    load()
  }

  return (
    <div>
      <div className="tab-header">
        <div>
          <p className="page-subtitle">{schedules.length} schedule{schedules.length !== 1 ? 's' : ''}</p>
        </div>
        <button className="btn-primary" onClick={() => { setEditing(null); setModalOpen(true) }}>
          + Add Schedule
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="loading">Loading…</div>
      ) : schedules.length === 0 ? (
        <div className="empty-state">
          <p>No schedules yet.</p>
          <button className="btn-primary" onClick={() => { setEditing(null); setModalOpen(true) }}>
            Add your first schedule
          </button>
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
                <th>Every</th>
                <th>Warn</th>
                <th>Source</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {schedules.map(s => (
                <tr key={s.id}>
                  <td className="fw-medium">{s.piano_name}<br /><span className="meta">{s.piano_brand}</span></td>
                  <td>{s.piano_location}</td>
                  <td>{s.task_name}</td>
                  <td><TaskBadge type={s.task_type} /></td>
                  <td>{s.interval_days}d</td>
                  <td>{s.warning_days_before}d</td>
                  <td>{s.template_name
                    ? <span className="template-pill">📋 {s.template_name}</span>
                    : <span className="meta">Manual</span>}
                  </td>
                  <td>
                    <span className={s.is_active ? 'status-active' : 'status-inactive'}>
                      {s.is_active ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td className="actions">
                    <button className="btn-edit" onClick={() => { setEditing(s); setModalOpen(true) }}>Edit</button>
                    <button className="btn-delete" onClick={() => setDeleteConfirm(s)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalOpen && (
        <ScheduleFormModal
          schedule={editing}
          onClose={() => setModalOpen(false)}
          onSaved={() => { setModalOpen(false); load() }}
        />
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Schedule</h3>
            <p>Delete <strong>{deleteConfirm.task_name}</strong> for <strong>{deleteConfirm.piano_name}</strong>?</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(null)}>Cancel</button>
              <button className="btn-danger" onClick={() => handleDelete(deleteConfirm)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Templates Tab ───────────────────────────────────────────────────────────

function TemplatesTab() {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [templateModal, setTemplateModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [applying, setApplying] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/schedule-templates/')
      .then(r => r.json())
      .then(data => { setTemplates(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load templates.'); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  async function handleDelete(t) {
    await fetch(`/api/schedule-templates/${t.id}/`, { method: 'DELETE' })
    setDeleteConfirm(null)
    load()
  }

  return (
    <div>
      <div className="tab-header">
        <div>
          <p className="page-subtitle">{templates.length} template{templates.length !== 1 ? 's' : ''}</p>
        </div>
        <button className="btn-primary" onClick={() => { setEditing(null); setTemplateModal(true) }}>
          + New Template
        </button>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="loading">Loading…</div>
      ) : templates.length === 0 ? (
        <div className="empty-state">
          <p>No templates yet.</p>
          <p className="meta">Templates let you apply a standard schedule to many pianos at once.</p>
          <button className="btn-primary" style={{ marginTop: '1rem' }}
            onClick={() => { setEditing(null); setTemplateModal(true) }}>
            Create your first template
          </button>
        </div>
      ) : (
        <div className="template-grid">
          {templates.map(t => (
            <div key={t.id} className="template-card">
              <div className="template-card-header">
                <TaskBadge type={t.task_type} />
                <span className="template-count">{t.schedule_count} piano{t.schedule_count !== 1 ? 's' : ''}</span>
              </div>
              <h3 className="template-name">{t.name}</h3>
              <p className="template-task">{t.task_name}</p>
              <div className="template-meta-row">
                <span>Every {t.interval_days} days</span>
                <span>Warn {t.warning_days_before}d before</span>
              </div>
              {t.description && <p className="template-desc">{t.description}</p>}
              <div className="template-actions">
                <button className="btn-apply" onClick={() => setApplying(t)}>
                  Apply to Pianos
                </button>
                <button className="btn-edit" onClick={() => { setEditing(t); setTemplateModal(true) }}>Edit</button>
                <button className="btn-delete" onClick={() => setDeleteConfirm(t)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {templateModal && (
        <TemplateFormModal
          template={editing}
          onClose={() => setTemplateModal(false)}
          onSaved={() => { setTemplateModal(false); load() }}
        />
      )}

      {applying && (
        <ApplyTemplateModal
          template={applying}
          onClose={() => setApplying(null)}
          onApplied={() => { setApplying(null); load() }}
        />
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Template</h3>
            <p>Delete template <strong>{deleteConfirm.name}</strong>? Existing schedules created from this template will remain.</p>
            <div className="confirm-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(null)}>Cancel</button>
              <button className="btn-danger" onClick={() => handleDelete(deleteConfirm)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function MaintenancePage() {
  const [tab, setTab] = useState('schedules')

  return (
    <div className="maintenance-page">
      <div className="page-header">
        <h2>Maintenance</h2>
      </div>

      <div className="tabs">
        <button
          className={`tab-btn ${tab === 'schedules' ? 'active' : ''}`}
          onClick={() => setTab('schedules')}
        >
          Schedules
        </button>
        <button
          className={`tab-btn ${tab === 'templates' ? 'active' : ''}`}
          onClick={() => setTab('templates')}
        >
          Templates
        </button>
      </div>

      <div className="tab-content">
        {tab === 'schedules' ? <SchedulesTab /> : <TemplatesTab />}
      </div>
    </div>
  )
}
