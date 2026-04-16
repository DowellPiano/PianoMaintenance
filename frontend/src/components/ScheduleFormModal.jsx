import { useState, useEffect } from 'react'
import './FormModal.css'

const TASK_TYPES = ['Tuning', 'Regulation', 'Voicing', 'Cleaning', 'Inspection', 'Other']

const EMPTY = {
  piano: '',
  task_name: '',
  task_type: 'Tuning',
  interval_days: 90,
  warning_days_before: 7,
  is_active: true,
}

export default function ScheduleFormModal({ schedule, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [pianos, setPianos] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/pianos/')
      .then(r => r.json())
      .then(data => setPianos(data.results ?? data))
  }, [])

  useEffect(() => {
    if (schedule) {
      setForm({
        piano: schedule.piano ?? '',
        task_name: schedule.task_name ?? '',
        task_type: schedule.task_type ?? 'Tuning',
        interval_days: schedule.interval_days ?? 90,
        warning_days_before: schedule.warning_days_before ?? 7,
        is_active: schedule.is_active ?? true,
      })
    } else {
      setForm(EMPTY)
    }
  }, [schedule])

  function handleChange(e) {
    const { name, value, type, checked } = e.target
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const url = schedule ? `/api/schedules/${schedule.id}/` : '/api/schedules/'
    const method = schedule ? 'PUT' : 'POST'
    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, piano: Number(form.piano) }),
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
          <h2>{schedule ? 'Edit Schedule' : 'Add Schedule'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="modal-error">{error}</div>}
        <form onSubmit={handleSubmit} className="piano-form">
          <label>
            Piano *
            <select name="piano" value={form.piano} onChange={handleChange} required>
              <option value="">— Select piano —</option>
              {pianos.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name} — {p.brand} ({p.location_name})
                </option>
              ))}
            </select>
          </label>

          <div className="form-row">
            <label>
              Task Name *
              <input name="task_name" value={form.task_name} onChange={handleChange} required />
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

          <label className="checkbox-label">
            <input type="checkbox" name="is_active" checked={form.is_active} onChange={handleChange} />
            Active
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : schedule ? 'Save Changes' : 'Add Schedule'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
