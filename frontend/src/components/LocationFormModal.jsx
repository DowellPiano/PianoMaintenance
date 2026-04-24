import { useState, useEffect } from 'react'
import { apiFetch } from '../api'
import { parseApiErrors } from '../formUtils'
import './FormModal.css'

export default function LocationFormModal({ location, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', building: '', address: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  useEffect(() => {
    if (location) {
      setForm({
        name:     location.name     || '',
        building: location.building || '',
        address:  location.address  || '',
      })
    } else {
      setForm({ name: '', building: '', address: '' })
    }
  }, [location])

  function handleChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
    if (fieldErrors[name]) setFieldErrors(fe => ({ ...fe, [name]: undefined }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})

    const url    = location ? `/api/locations/${location.id}/` : '/api/locations/'
    const method = location ? 'PUT' : 'POST'

    try {
      const res = await apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        const { fields, banner } = parseApiErrors(data)
        setFieldErrors(fields)
        setError(banner)
      } else {
        onSaved()
      }
    } catch {
      setError('Network error — is Django running?')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{location ? 'Edit Location' : 'Add Location'}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <label>
            Name <span className="required">*</span>
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder="e.g. Main Hall"
              required
              className={fieldErrors.name ? 'input-error' : undefined}
            />
            {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
          </label>

          <label>
            Building
            <input
              name="building"
              value={form.building}
              onChange={handleChange}
              placeholder="e.g. Smith Music Center"
              className={fieldErrors.building ? 'input-error' : undefined}
            />
            {fieldErrors.building && <span className="field-error">{fieldErrors.building}</span>}
          </label>

          <label>
            Address
            <textarea
              name="address"
              value={form.address}
              onChange={handleChange}
              placeholder="123 Main St, City, State 12345"
              rows={3}
              className={fieldErrors.address ? 'input-error' : undefined}
            />
            {fieldErrors.address && <span className="field-error">{fieldErrors.address}</span>}
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
