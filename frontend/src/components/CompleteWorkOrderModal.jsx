import { useState } from 'react'
import './FormModal.css'

export default function CompleteWorkOrderModal({ workOrder, onClose, onCompleted }) {
  const [form, setForm] = useState({
    hours_worked: '',
    work_performed: '',
    notes: '',
  })
  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState(null)

  function handleChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.hours_worked || Number(form.hours_worked) < 0.25) {
      setError('Hours worked must be at least 0.25.')
      return
    }
    if (!form.work_performed.trim()) {
      setError('Please describe the work performed.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const r = await fetch(`/api/work-orders/${workOrder.id}/complete/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hours_worked: Number(form.hours_worked),
          work_performed: form.work_performed,
          notes: form.notes,
        }),
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        setError(data.detail || JSON.stringify(data) || 'Failed to complete work order.')
      } else {
        onCompleted()
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
            <p className="modal-subtitle">WO #{workOrder.id} — {workOrder.piano_name ?? workOrder.piano}</p>
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
              min="0.25"
              step="0.25"
              placeholder="e.g. 1.5"
              required
            />
          </label>

          <label>
            Work Performed *
            <textarea
              name="work_performed"
              value={form.work_performed}
              onChange={handleChange}
              rows={4}
              placeholder="Describe what was done…"
              required
            />
          </label>

          <label>
            Additional Notes
            <textarea
              name="notes"
              value={form.notes}
              onChange={handleChange}
              rows={3}
              placeholder="Any observations, parts used, follow-up needed…"
            />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-complete" disabled={saving}>
              {saving ? 'Saving…' : 'Mark Complete'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
