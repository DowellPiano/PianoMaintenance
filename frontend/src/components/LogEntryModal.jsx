import { useState } from 'react'
import { apiFetch } from '../api'
import { parseApiErrors } from '../formUtils'
import './FormModal.css'

export default function LogEntryModal({ workOrder, onClose, onSaved }) {
  const [form, setForm] = useState({ hours_worked: '', work_performed: '', notes: '' })
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
      const res = await apiFetch(`/api/work-orders/${workOrder.id}/complete/`, {
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
          <div>
            <h2>Complete Work Order</h2>
            <p className="modal-subtitle">
              {workOrder.piano_name} — {workOrder.order_type}
            </p>
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <label>
            Hours Worked *
            <input
              type="number"
              name="hours_worked"
              value={form.hours_worked}
              onChange={handleChange}
              min="0"
              step="any"
              required
              placeholder="e.g. 1.5"
              className={fieldErrors.hours_worked ? 'input-error' : undefined}
            />
            {fieldErrors.hours_worked && <span className="field-error">{fieldErrors.hours_worked}</span>}
          </label>

          <label>
            Work Performed *
            <textarea
              name="work_performed"
              value={form.work_performed}
              onChange={handleChange}
              rows={4}
              required
              placeholder="Describe the work completed…"
              className={fieldErrors.work_performed ? 'input-error' : undefined}
            />
            {fieldErrors.work_performed && <span className="field-error">{fieldErrors.work_performed}</span>}
          </label>

          <label>
            Notes
            <textarea
              name="notes"
              value={form.notes}
              onChange={handleChange}
              rows={3}
              placeholder="Any additional notes or observations…"
            />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Mark Complete'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
