import { useState, useEffect, useCallback } from 'react'
import './TechniciansPage.css'

const EMPTY_FORM = {
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  specialization: '',
}

function TechnicianFormModal({ technician, onClose, onSaved }) {
  const [form,   setForm]   = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState(null)

  useEffect(() => {
    if (technician) {
      setForm({
        first_name:     technician.first_name     ?? '',
        last_name:      technician.last_name      ?? '',
        email:          technician.email          ?? '',
        phone:          technician.phone          ?? '',
        specialization: technician.specialization ?? '',
      })
    } else {
      setForm(EMPTY_FORM)
    }
  }, [technician])

  function handleChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const url    = technician ? `/api/technicians/${technician.id}/` : '/api/technicians/'
    const method = technician ? 'PUT' : 'POST'
    try {
      const r = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        setError(data.detail || JSON.stringify(data) || 'Save failed.')
      } else {
        onSaved()
      }
    } catch {
      setError('Network error.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{technician ? 'Edit Technician' : 'Add Technician'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="modal-error">{error}</div>}
        <form onSubmit={handleSubmit} className="piano-form">
          <div className="form-row">
            <label>First Name *<input name="first_name" value={form.first_name} onChange={handleChange} required /></label>
            <label>Last Name *<input  name="last_name"  value={form.last_name}  onChange={handleChange} required /></label>
          </div>
          <div className="form-row">
            <label>Email<input type="email" name="email" value={form.email} onChange={handleChange} /></label>
            <label>Phone<input name="phone" value={form.phone} onChange={handleChange} /></label>
          </div>
          <label>
            Specialization
            <input name="specialization" value={form.specialization} onChange={handleChange} placeholder="e.g. Tuning, Regulation…" />
          </label>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : technician ? 'Save Changes' : 'Add Technician'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function TechniciansPage() {
  const [technicians,   setTechnicians]   = useState([])
  const [loading,       setLoading]       = useState(true)
  const [error,         setError]         = useState(null)
  const [modalOpen,     setModalOpen]     = useState(false)
  const [editing,       setEditing]       = useState(null)
  const [showInactive,  setShowInactive]  = useState(false)

  const loadTechnicians = useCallback(() => {
    setLoading(true)
    fetch('/api/technicians/')
      .then(r => r.json())
      .then(d => { setTechnicians(d.results ?? d); setLoading(false) })
      .catch(() => { setError('Failed to load technicians.'); setLoading(false) })
  }, [])

  useEffect(() => { loadTechnicians() }, [loadTechnicians])

  async function handleReactivate(tech) {
    setError(null)
    try {
      const r = await fetch(`/api/technicians/${tech.id}/reactivate/`, { method: 'POST' })
      if (r.ok) {
        loadTechnicians()
      } else {
        const data = await r.json().catch(() => ({}))
        setError(data.detail || `Reactivate failed (HTTP ${r.status}).`)
      }
    } catch {
      setError('Reactivate failed — network error.')
    }
  }

  async function handleDeactivate(tech) {
    setError(null)
    try {
      const r = await fetch(`/api/technicians/${tech.id}/deactivate/`, { method: 'POST' })
      if (r.ok) {
        loadTechnicians()
      } else {
        const data = await r.json().catch(() => ({}))
        setError(data.detail || `Deactivate failed (HTTP ${r.status}).`)
      }
    } catch {
      setError('Deactivate failed — network error.')
    }
  }

  const active   = technicians.filter(t => t.is_active !== false)
  const inactive = technicians.filter(t => t.is_active === false)
  const displayed = showInactive ? technicians : active

  return (
    <div className="tech-page">
      <div className="page-header">
        <div>
          <h2>Technicians</h2>
          <p className="page-subtitle">
            {active.length} active{inactive.length > 0 ? `, ${inactive.length} inactive` : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {inactive.length > 0 && (
            <label className="show-inactive-toggle">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={e => setShowInactive(e.target.checked)}
              />
              Show inactive
            </label>
          )}
          <button className="btn-primary" onClick={() => { setEditing(null); setModalOpen(true) }}>
            + Add Technician
          </button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="loading">Loading…</div>
      ) : displayed.length === 0 ? (
        <div className="empty-state">
          <p>No technicians yet.</p>
          <button className="btn-primary" onClick={() => { setEditing(null); setModalOpen(true) }}>
            Add your first technician
          </button>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="tech-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Specialization</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {displayed.map(t => (
                <tr key={t.id} className={t.is_active === false ? 'row-inactive' : ''}>
                  <td className="fw-medium">
                    {t.full_name ?? `${t.first_name} ${t.last_name}`}
                  </td>
                  <td>{t.email || <span className="empty">—</span>}</td>
                  <td>{t.phone || <span className="empty">—</span>}</td>
                  <td>{t.specialization || <span className="empty">—</span>}</td>
                  <td>
                    {t.is_active === false ? (
                      <span className="badge status-inactive">Inactive</span>
                    ) : (
                      <span className="badge status-active">Active</span>
                    )}
                  </td>
                  <td className="actions">
                    <button className="btn-edit" onClick={() => { setEditing(t); setModalOpen(true) }}>
                      Edit
                    </button>
                    {t.is_active === false ? (
                      <button className="btn-reactivate" onClick={() => handleReactivate(t)}>
                        Reactivate
                      </button>
                    ) : (
                      <button className="btn-deactivate" onClick={() => handleDeactivate(t)}>
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalOpen && (
        <TechnicianFormModal
          technician={editing}
          onClose={() => { setModalOpen(false); setEditing(null) }}
          onSaved={() => { setModalOpen(false); setEditing(null); loadTechnicians() }}
        />
      )}
    </div>
  )
}
