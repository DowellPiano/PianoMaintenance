import { useState, useEffect } from 'react'
import './FormModal.css'

export default function LocationFormModal({ location, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', building: '', address: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)

  useEffect(() => {
    if (location) {
      setForm({
        name:     location.name     || '',
        building: location.building || '',
        address:  location.address  || '',
      })
    }
  }, [location])

  function handleChange(e) {
    setForm(f => ({ ...f, [e.target.name]: e.target.value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.name.trim()) { setError('Name is required.'); return }
    setSaving(true)
    setError(null)

    const url    = location ? `/api/locations/${location.id}/` : '/api/locations/'
    const method = location ? 'PUT' : 'POST'

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(Object.values(data).flat().join(' ') || 'Save failed.')
      }
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{location ? 'Edit Location' : 'Add Location'}</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="modal-form">
          <label>
            Name <span className="required">*</span>
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder="e.g. Main Hall"
              required
            />
          </label>

          <label>
            Building
            <input
              name="building"
              value={form.building}
              onChange={handleChange}
              placeholder="e.g. Smith Music Center"
            />
          </label>

          <label>
            Address
            <textarea
              name="address"
              value={form.address}
              onChange={handleChange}
              placeholder="123 Main St, City, State 12345"
              rows={3}
            />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : location ? 'Save Changes' : 'Add Location'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
