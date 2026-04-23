import { useState, useEffect } from 'react'
import './FormModal.css'

const PRIORITIES = ['Low', 'Normal', 'High', 'Urgent']

export default function StartWorkOrderModal({ piano, schedule, onClose, onSaved }) {
  const [technicians, setTechnicians] = useState([])
  const [form, setForm] = useState({
    assigned_tech: '',
    priority: 'Normal',
    description: schedule?.task_name ? `${schedule.task_name} — ` : '',
    due_date: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)

  useEffect(() => {
    fetch('/api/technicians/')
      .then(r => r.json())
      .then(d => setTechnicians(d.results ?? d))
      .catch(() => setError('Failed to load technicians.'))
  }, [])

  function handleChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const body = {
        piano: piano.id,
        schedule: schedule?.id ?? null,
        assigned_tech: form.assigned_tech ? Number(form.assigned_tech) : null,
        order_type: 'Preventive',
        status: 'Open',
        priority: form.priority,
        description: form.description,
        due_date: form.due_date || null,
      }
      const r = await fetch('/api/work-orders/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        setError(data.detail || JSON.stringify(data) || 'Failed to create work order.')
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
            <h2>Start Work Order</h2>
            <p className="modal-subtitle">
              {piano.name}
              {schedule ? ` — ${schedule.task_name}` : ''}
            </p>
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <div className="form-row">
            <label>
              Assigned Technician
              <select name="assigned_tech" value={form.assigned_tech} onChange={handleChange}>
                <option value="">— Unassigned —</option>
                {technicians.filter(t => t.is_active !== false).map(t => (
                  <option key={t.id} value={t.id}>{t.full_name ?? `${t.first_name} ${t.last_name}`}</option>
                ))}
              </select>
            </label>
            <label>
              Priority
              <select name="priority" value={form.priority} onChange={handleChange}>
                {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>

          <label>
            Due Date
            <input type="date" name="due_date" value={form.due_date} onChange={handleChange} />
          </label>

          <label>
            Description
            <textarea
              name="description"
              value={form.description}
              onChange={handleChange}
              rows={4}
              placeholder="Describe the work to be performed…"
            />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Creating…' : 'Create Work Order'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
