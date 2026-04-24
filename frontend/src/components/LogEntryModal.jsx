import { useState, useEffect } from 'react'
import { apiFetch } from '../api'
import { parseApiErrors } from '../formUtils'
import './FormModal.css'

const EMPTY_CONDITION = {
  overall_rating: '',
  pitch_offset_cents: '',
  humidity_pct: '',
  temperature_f: '',
  condition_notes: '',
}

function conditionHasData(c) {
  return c.overall_rating || c.pitch_offset_cents !== '' || c.humidity_pct !== '' ||
    c.temperature_f !== '' || c.condition_notes
}

export default function LogEntryModal({ workOrder, onClose, onSaved }) {
  const [form, setForm]           = useState({ hours_worked: '', work_performed: '', notes: '' })
  const [condition, setCondition] = useState(EMPTY_CONDITION)
  const [partsRows, setPartsRows] = useState([])   // [{ part: '', quantity_used: 1 }]
  const [parts, setParts]         = useState([])
  const [saving, setSaving]       = useState(false)
  const [error, setError]         = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  // Fetch parts list for the dropdown
  useEffect(() => {
    apiFetch('/api/parts/')
      .then(r => r.json())
      .then(data => setParts(data.results ?? data))
      .catch(() => {})
  }, [])

  function handleChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
    if (fieldErrors[name]) setFieldErrors(fe => ({ ...fe, [name]: undefined }))
  }

  function handleConditionChange(e) {
    const { name, value } = e.target
    setCondition(c => ({ ...c, [name]: value }))
  }

  function addPartRow() {
    setPartsRows(rows => [...rows, { part: '', quantity_used: 1 }])
  }

  function removePartRow(idx) {
    setPartsRows(rows => rows.filter((_, i) => i !== idx))
  }

  function updatePartRow(idx, field, value) {
    setPartsRows(rows => rows.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})

    try {
      // Step 1: complete the work order → get the new log id
      const res = await apiFetch(`/api/work-orders/${workOrder.id}/complete/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hours_worked:  form.hours_worked,
          work_performed: form.work_performed,
          notes:         form.notes,
        }),
      })

      if (!res.ok) {
        const data = await res.json()
        const { fields, banner } = parseApiErrors(data)
        setFieldErrors(fields)
        setError(banner)
        return
      }

      const completed = await res.json()
      const logId     = completed.log?.id

      // Step 2: optional condition reading
      if (logId && conditionHasData(condition)) {
        const crBody = {
          piano: workOrder.piano,
          log:   logId,
        }
        if (condition.overall_rating)     crBody.overall_rating     = condition.overall_rating
        if (condition.pitch_offset_cents !== '') crBody.pitch_offset_cents = condition.pitch_offset_cents
        if (condition.humidity_pct !== '')       crBody.humidity_pct       = condition.humidity_pct
        if (condition.temperature_f !== '')      crBody.temperature_f      = condition.temperature_f
        if (condition.condition_notes)           crBody.notes              = condition.condition_notes
        await apiFetch('/api/condition-readings/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(crBody),
        })
      }

      // Step 3: parts used
      if (logId) {
        const validParts = partsRows.filter(r => r.part && r.quantity_used > 0)
        await Promise.all(validParts.map(r =>
          apiFetch('/api/parts-used/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ log: logId, part: Number(r.part), quantity_used: Number(r.quantity_used) }),
          })
        ))
      }

      onSaved()
    } catch {
      setError('Network error — is Django running?')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal log-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>Complete Work Order</h2>
            <p className="modal-subtitle">{workOrder.piano_name} — {workOrder.order_type}</p>
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          {/* ── Core log fields ── */}
          <label>
            Hours Worked *
            <input
              type="number" name="hours_worked" value={form.hours_worked}
              onChange={handleChange} min="0" step="any" required placeholder="e.g. 1.5"
              className={fieldErrors.hours_worked ? 'input-error' : undefined}
            />
            {fieldErrors.hours_worked && <span className="field-error">{fieldErrors.hours_worked}</span>}
          </label>

          <label>
            Work Performed *
            <textarea
              name="work_performed" value={form.work_performed} onChange={handleChange}
              rows={4} required placeholder="Describe the work completed…"
              className={fieldErrors.work_performed ? 'input-error' : undefined}
            />
            {fieldErrors.work_performed && <span className="field-error">{fieldErrors.work_performed}</span>}
          </label>

          <label>
            Notes
            <textarea name="notes" value={form.notes} onChange={handleChange} rows={2}
              placeholder="Any additional notes or observations…" />
          </label>

          {/* ── Condition Reading ── */}
          <div className="log-section-header">Condition Reading <span className="log-optional">(optional)</span></div>

          <div className="form-row">
            <label>
              Overall Rating
              <select name="overall_rating" value={condition.overall_rating} onChange={handleConditionChange}>
                <option value="">— Select —</option>
                <option value="Poor">Poor</option>
                <option value="Fair">Fair</option>
                <option value="Good">Good</option>
                <option value="Excellent">Excellent</option>
              </select>
            </label>
            <label>
              Pitch Offset (cents)
              <input type="number" name="pitch_offset_cents" value={condition.pitch_offset_cents}
                onChange={handleConditionChange} step="0.01" placeholder="e.g. -2.5" />
            </label>
          </div>

          <div className="form-row">
            <label>
              Humidity (%)
              <input type="number" name="humidity_pct" value={condition.humidity_pct}
                onChange={handleConditionChange} min="0" max="100" step="0.1" placeholder="e.g. 45.0" />
            </label>
            <label>
              Temperature (°F)
              <input type="number" name="temperature_f" value={condition.temperature_f}
                onChange={handleConditionChange} step="0.1" placeholder="e.g. 70.0" />
            </label>
          </div>

          <label>
            Condition Notes
            <textarea name="condition_notes" value={condition.condition_notes}
              onChange={handleConditionChange} rows={2} placeholder="Observations about piano condition…" />
          </label>

          {/* ── Parts Used ── */}
          <div className="log-section-header">
            Parts Used <span className="log-optional">(optional)</span>
            <button type="button" className="btn-add-part" onClick={addPartRow}>+ Add Part</button>
          </div>

          {partsRows.length > 0 && (
            <div className="parts-rows">
              {partsRows.map((row, idx) => (
                <div key={idx} className="part-row">
                  <select
                    value={row.part}
                    onChange={e => updatePartRow(idx, 'part', e.target.value)}
                    className="part-select"
                  >
                    <option value="">— Select part —</option>
                    {parts.map(p => (
                      <option key={p.id} value={p.id}>
                        {p.name}{p.part_number ? ` (${p.part_number})` : ''} — {p.stock_quantity} in stock
                      </option>
                    ))}
                  </select>
                  <input
                    type="number" min="1" value={row.quantity_used}
                    onChange={e => updatePartRow(idx, 'quantity_used', e.target.value)}
                    className="part-qty"
                    placeholder="Qty"
                  />
                  <button type="button" className="btn-remove-part" onClick={() => removePartRow(idx)}>×</button>
                </div>
              ))}
            </div>
          )}

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
