import { useState, useEffect } from 'react'
import './FormModal.css'

const TASK_TYPES = ['Tuning', 'Regulation', 'Voicing', 'Cleaning', 'Inspection', 'Other']

const EMPTY = {
  name: '',
  task_name: '',
  task_type: 'Tuning',
  interval_days: 90,
  warning_days_before: 7,
  description: '',
}

export default function TemplateFormModal({ template, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (template) {
      setForm({
        name: template.name ?? '',
        task_name: template.task_name ?? '',
        task_type: template.task_type ?? 'Tuning',
        interval_days: template.interval_days ?? 90,
        warning_days_before: template.warning_days_before ?? 7,
        description: template.description ?? '',
      })
    } else {
      setForm(EMPTY)
    }
  }, [template])

  function handleChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const url = template ? `/api/schedule-templates/${template.id}/` : '/api/schedule-templates/'
    const method = template ? 'PUT' : 'POST'
    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const data = await res.json()
        setError(JSON.stringify(data))
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
          <h2>{template ? 'Edit Template' : 'New Template'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="modal-error">{error}</div>}
        <form onSubmit={handleSubmit} className="piano-form">
          <label>
            Template Name *
            <input name="name" value={form.name} onChange={handleChange} required
              placeholder="e.g. Annual Tuning" />
          </label>

          <div className="form-row">
            <label>
              Task Name *
              <input name="task_name" value={form.task_name} onChange={handleChange} required
                placeholder="e.g. Full Tuning" />
            </label>
            <label>
              Task Type *
              <select name="task_type" value={form.task_type} onChange={handleChange} required>
                {TASK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>

          <div className="form-row">
            <label>
              Interval (days) *
              <input type="number" name="interval_days" value={form.interval_days}
                onChange={handleChange} min={1} required />
            </label>
            <label>
              Warning (days before) *
              <input type="number" name="warning_days_before" value={form.warning_days_before}
                onChange={handleChange} min={0} required />
            </label>
          </div>

          <label>
            Description
            <textarea name="description" value={form.description} onChange={handleChange}
              rows={3} placeholder="Optional notes about this template…" />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : template ? 'Save Changes' : 'Create Template'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
