import { useState, useEffect } from 'react'
import { apiFetch } from '../api'
import { parseApiErrors } from '../formUtils'
import './FormModal.css'

const EMPTY = { name: '', part_number: '', supplier: '', unit_cost: '', stock_quantity: '', reorder_threshold: '' }

export default function PartFormModal({ part, onClose, onSaved }) {
  const [form, setForm]           = useState(EMPTY)
  const [saving, setSaving]       = useState(false)
  const [error, setError]         = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  useEffect(() => {
    if (part) {
      setForm({
        name:               part.name               ?? '',
        part_number:        part.part_number        ?? '',
        supplier:           part.supplier           ?? '',
        unit_cost:          part.unit_cost          ?? '',
        stock_quantity:     part.stock_quantity     ?? '',
        reorder_threshold:  part.reorder_threshold  ?? '',
      })
    } else {
      setForm(EMPTY)
    }
  }, [part])

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
    const url    = part ? `/api/parts/${part.id}/` : '/api/parts/'
    const method = part ? 'PUT' : 'POST'
    try {
      const res = await apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          unit_cost:         form.unit_cost         !== '' ? Number(form.unit_cost)         : null,
          stock_quantity:    form.stock_quantity     !== '' ? Number(form.stock_quantity)    : 0,
          reorder_threshold: form.reorder_threshold !== '' ? Number(form.reorder_threshold) : 0,
        }),
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
          <h2>{part ? 'Edit Part' : 'Add Part'}</h2>
          <button type="button" className="modal-close" onClick={onClose}>×</button>
        </div>
        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <div className="form-row">
            <label>
              Name *
              <input name="name" value={form.name} onChange={handleChange} required
                className={fieldErrors.name ? 'input-error' : undefined} />
              {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
            </label>
            <label>
              Part Number
              <input name="part_number" value={form.part_number} onChange={handleChange} placeholder="e.g. STW-1234" />
            </label>
          </div>

          <div className="form-row">
            <label>
              Supplier
              <input name="supplier" value={form.supplier} onChange={handleChange} placeholder="Supplier name" />
            </label>
            <label>
              Unit Cost ($)
              <input type="number" name="unit_cost" value={form.unit_cost} onChange={handleChange}
                min="0" step="0.01" placeholder="0.00" />
            </label>
          </div>

          <div className="form-row">
            <label>
              Stock Quantity *
              <input type="number" name="stock_quantity" value={form.stock_quantity} onChange={handleChange}
                min="0" step="1" required placeholder="0"
                className={fieldErrors.stock_quantity ? 'input-error' : undefined} />
              {fieldErrors.stock_quantity && <span className="field-error">{fieldErrors.stock_quantity}</span>}
            </label>
            <label>
              Reorder Threshold
              <input type="number" name="reorder_threshold" value={form.reorder_threshold} onChange={handleChange}
                min="0" step="1" placeholder="0" />
            </label>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : part ? 'Save Changes' : 'Add Part'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
