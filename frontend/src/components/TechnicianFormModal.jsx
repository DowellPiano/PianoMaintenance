import { useState } from 'react'
import { apiFetch } from '../api'
import { parseApiErrors } from '../formUtils'
import './FormModal.css'

const EMPTY = { first_name: '', last_name: '', username: '', email: '', password: '', is_staff: false }

export default function TechnicianFormModal({ onClose, onSaved }) {
  const [form, setForm]               = useState(EMPTY)
  const [saving, setSaving]           = useState(false)
  const [error, setError]             = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  function handleChange(e) {
    const { name, value, type, checked } = e.target
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }))
    if (fieldErrors[name]) setFieldErrors(fe => ({ ...fe, [name]: undefined }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const res = await apiFetch('/api/technicians/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const data = await res.json()
        const { fields, banner } = parseApiErrors(data)
        setFieldErrors(fields)
        setError(banner)
      } else {
        onSaved(await res.json())
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
          <h2>Add Technician</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <div className="form-row">
            <label>
              First Name
              <input name="first_name" value={form.first_name} onChange={handleChange}
                className={fieldErrors.first_name ? 'input-error' : undefined} />
              {fieldErrors.first_name && <span className="field-error">{fieldErrors.first_name}</span>}
            </label>
            <label>
              Last Name *
              <input name="last_name" value={form.last_name} onChange={handleChange} required
                className={fieldErrors.last_name ? 'input-error' : undefined} />
              {fieldErrors.last_name && <span className="field-error">{fieldErrors.last_name}</span>}
            </label>
          </div>

          <div className="form-row">
            <label>
              Username *
              <input name="username" value={form.username} onChange={handleChange} required
                className={fieldErrors.username ? 'input-error' : undefined} />
              {fieldErrors.username && <span className="field-error">{fieldErrors.username}</span>}
            </label>
            <label>
              Email
              <input type="email" name="email" value={form.email} onChange={handleChange}
                className={fieldErrors.email ? 'input-error' : undefined} />
              {fieldErrors.email && <span className="field-error">{fieldErrors.email}</span>}
            </label>
          </div>

          <label>
            Password *
            <input type="password" name="password" value={form.password} onChange={handleChange} required
              placeholder="Set initial password"
              className={fieldErrors.password ? 'input-error' : undefined} />
            {fieldErrors.password && <span className="field-error">{fieldErrors.password}</span>}
          </label>

          <label className="checkbox-label">
            <input type="checkbox" name="is_staff" checked={form.is_staff} onChange={handleChange} />
            Staff / Admin access
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Add Technician'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
