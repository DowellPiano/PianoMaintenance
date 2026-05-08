import { useState } from 'react'
import { apiFetch } from '../api'
import { parseApiErrors } from '../formUtils'
import './FormModal.css'

export default function TeamFormModal({ team, techs, onClose, onSaved }) {
  const isEdit = team !== null
  const [form, setForm] = useState({
    name: team?.name ?? '',
    manager: team?.manager ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

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
    try {
      const url = isEdit ? `/api/teams/${team.id}/` : '/api/teams/'
      const payload = { ...form, manager: form.manager || null }
      const res = await apiFetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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
          <h2>{isEdit ? 'Edit Team' : 'Create Team'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <label>
            Team Name *
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              required
              className={fieldErrors.name ? 'input-error' : undefined}
            />
            {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
          </label>

          <label>
            Manager
            <select name="manager" value={form.manager} onChange={handleChange}>
              <option value="">— None —</option>
              {techs.filter(t => t.is_active !== false).map(t => (
                <option key={t.id} value={t.id}>
                  {t.full_name ?? `${t.first_name} ${t.last_name}`}
                </option>
              ))}
            </select>
            {fieldErrors.manager && <span className="field-error">{fieldErrors.manager}</span>}
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : (isEdit ? 'Save Changes' : 'Create Team')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
