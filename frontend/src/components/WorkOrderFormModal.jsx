import { useState, useEffect } from 'react'
import { apiFetch } from '../api'
import { parseApiErrors } from '../formUtils'
import './FormModal.css'

const EMPTY = {
  piano: '',
  assigned_tech: '',
  order_type: 'Preventive',
  status: 'Open',
  priority: 'Normal',
  description: '',
  due_date: '',
  completed_date: '',
}

export default function WorkOrderFormModal({ workOrder, prefill, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY)
  const [pianos, setPianos] = useState([])
  const [techs, setTechs] = useState([])
  const [saving, setSaving] = useState(false)
  const [loadingDropdowns, setLoadingDropdowns] = useState(true)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  useEffect(() => {
    setLoadingDropdowns(true)
    Promise.all([
      apiFetch('/api/pianos/').then(r => r.json()),
      apiFetch('/api/technicians/').then(r => r.json()),
    ]).then(([pData, tData]) => {
      setPianos(pData.results ?? pData)
      setTechs(tData.results ?? tData)
      setLoadingDropdowns(false)
    }).catch(() => setLoadingDropdowns(false))
  }, [])

  useEffect(() => {
    if (workOrder) {
      setForm({
        piano:          workOrder.piano          ?? '',
        assigned_tech:  workOrder.assigned_tech  ?? '',
        order_type:     workOrder.order_type     ?? 'Preventive',
        status:         workOrder.status         ?? 'Open',
        priority:       workOrder.priority       ?? 'Normal',
        description:    workOrder.description    ?? '',
        due_date:       workOrder.due_date       ?? '',
        completed_date: workOrder.completed_date ?? '',
      })
    } else if (prefill) {
      setForm(f => ({ ...EMPTY, ...prefill }))
    } else {
      setForm(EMPTY)
    }
  }, [workOrder, prefill])

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
    const url    = workOrder ? `/api/work-orders/${workOrder.id}/` : '/api/work-orders/'
    const method = workOrder ? 'PUT' : 'POST'
    try {
      const body = {
        ...form,
        piano:          Number(form.piano) || null,
        assigned_tech:  form.assigned_tech ? Number(form.assigned_tech) : null,
        due_date:       form.due_date       || null,
        completed_date: form.completed_date || null,
      }
      const res = await apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
          <h2>{workOrder ? 'Edit Work Order' : 'New Work Order'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <label>
            Piano *
            <select
              name="piano"
              value={form.piano}
              onChange={handleChange}
              required
              disabled={loadingDropdowns}
              className={fieldErrors.piano ? 'input-error' : undefined}
            >
              <option value="">{loadingDropdowns ? 'Loading…' : '— Select piano —'}</option>
              {pianos.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name} — {p.make} ({p.location_name})
                </option>
              ))}
            </select>
            {fieldErrors.piano && <span className="field-error">{fieldErrors.piano}</span>}
          </label>

          <div className="form-row">
            <label>
              Order Type *
              <select
                name="order_type"
                value={form.order_type}
                onChange={handleChange}
                required
                className={fieldErrors.order_type ? 'input-error' : undefined}
              >
                <option value="Preventive">Preventive</option>
                <option value="Request">Request</option>
                <option value="Emergency">Emergency</option>
              </select>
              {fieldErrors.order_type && <span className="field-error">{fieldErrors.order_type}</span>}
            </label>
            <label>
              Priority *
              <select
                name="priority"
                value={form.priority}
                onChange={handleChange}
                required
                className={fieldErrors.priority ? 'input-error' : undefined}
              >
                <option value="Low">Low</option>
                <option value="Normal">Normal</option>
                <option value="High">High</option>
                <option value="Urgent">Urgent</option>
              </select>
              {fieldErrors.priority && <span className="field-error">{fieldErrors.priority}</span>}
            </label>
          </div>

          <div className="form-row">
            <label>
              Status *
              <select
                name="status"
                value={form.status}
                onChange={handleChange}
                required
                className={fieldErrors.status ? 'input-error' : undefined}
              >
                <option value="Open">Open</option>
                <option value="In Progress">In Progress</option>
                <option value="Complete">Complete</option>
                <option value="Cancelled">Cancelled</option>
              </select>
              {fieldErrors.status && <span className="field-error">{fieldErrors.status}</span>}
            </label>
            <label>
              Assigned Technician
              <select
                name="assigned_tech"
                value={form.assigned_tech}
                onChange={handleChange}
                disabled={loadingDropdowns}
                className={fieldErrors.assigned_tech ? 'input-error' : undefined}
              >
                <option value="">{loadingDropdowns ? 'Loading…' : '— Unassigned —'}</option>
                {techs.map(t => (
                  <option key={t.id} value={t.id}>{t.full_name}</option>
                ))}
              </select>
              {fieldErrors.assigned_tech && <span className="field-error">{fieldErrors.assigned_tech}</span>}
            </label>
          </div>

          <div className="form-row">
            <label>
              Due Date
              <input
                type="date"
                name="due_date"
                value={form.due_date}
                onChange={handleChange}
                className={fieldErrors.due_date ? 'input-error' : undefined}
              />
              {fieldErrors.due_date && <span className="field-error">{fieldErrors.due_date}</span>}
            </label>
            <label>
              Completed Date
              <input
                type="date"
                name="completed_date"
                value={form.completed_date}
                onChange={handleChange}
                className={fieldErrors.completed_date ? 'input-error' : undefined}
              />
              {fieldErrors.completed_date && <span className="field-error">{fieldErrors.completed_date}</span>}
            </label>
          </div>

          <label>
            Description
            <textarea
              name="description"
              value={form.description}
              onChange={handleChange}
              rows={3}
              placeholder="Describe the work to be done…"
              className={fieldErrors.description ? 'input-error' : undefined}
            />
            {fieldErrors.description && <span className="field-error">{fieldErrors.description}</span>}
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : workOrder ? 'Save Changes' : 'Create Work Order'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
