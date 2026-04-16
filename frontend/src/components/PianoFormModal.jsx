import { useState, useEffect } from 'react'
import './PianoFormModal.css'

const EMPTY_FORM = {
  name: '',
  brand: '',
  model: '',
  serial_number: '',
  piano_type: 'Grand',
  location: '',
  date_acquired: '',
  notes: '',
}

export default function PianoFormModal({ piano, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [locations, setLocations] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/locations/')
      .then(r => r.json())
      .then(data => setLocations(data.results ?? data))
      .catch(() => setError('Failed to load locations.'))
  }, [])

  useEffect(() => {
    if (piano) {
      setForm({
        name: piano.name ?? '',
        brand: piano.brand ?? '',
        model: piano.model ?? '',
        serial_number: piano.serial_number ?? '',
        piano_type: piano.piano_type ?? 'Grand',
        location: piano.location ?? '',
        date_acquired: piano.date_acquired ?? '',
        notes: piano.notes ?? '',
      })
    } else {
      setForm(EMPTY_FORM)
    }
  }, [piano])

  function handleChange(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)

    const url = piano ? `/api/pianos/${piano.id}/` : '/api/pianos/'
    const method = piano ? 'PUT' : 'POST'

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          location: Number(form.location) || null,
          date_acquired: form.date_acquired || null,
        }),
      })
      if (!res.ok) {
        const data = await res.json()
        setError(JSON.stringify(data))
      } else {
        const saved = await res.json()
        onSaved(saved)
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
          <h2>{piano ? 'Edit Piano' : 'Add Piano'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        {error && <div className="modal-error">{error}</div>}

        <form onSubmit={handleSubmit} className="piano-form">
          <div className="form-row">
            <label>
              Name *
              <input name="name" value={form.name} onChange={handleChange} required />
            </label>
            <label>
              Brand *
              <input name="brand" value={form.brand} onChange={handleChange} required />
            </label>
          </div>

          <div className="form-row">
            <label>
              Model
              <input name="model" value={form.model} onChange={handleChange} />
            </label>
            <label>
              Serial Number
              <input name="serial_number" value={form.serial_number} onChange={handleChange} />
            </label>
          </div>

          <div className="form-row">
            <label>
              Type *
              <select name="piano_type" value={form.piano_type} onChange={handleChange} required>
                <option value="Grand">Grand</option>
                <option value="Upright">Upright</option>
                <option value="Digital">Digital</option>
              </select>
            </label>
            <label>
              Location *
              <select name="location" value={form.location} onChange={handleChange} required>
                <option value="">— Select location —</option>
                {locations.map(l => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-row">
            <label>
              Date Acquired
              <input type="date" name="date_acquired" value={form.date_acquired} onChange={handleChange} />
            </label>
          </div>

          <label>
            Notes
            <textarea name="notes" value={form.notes} onChange={handleChange} rows={3} />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : piano ? 'Save Changes' : 'Add Piano'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
