import { useState, useEffect } from 'react'
import { apiFetch } from '../api'
import './FormModal.css'
import './ApplyTemplateModal.css'

export default function ApplyTemplateModal({ template, onClose, onApplied }) {
  const [pianos, setPianos] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [applying, setApplying] = useState(false)
  const [loadingPianos, setLoadingPianos] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  useEffect(() => {
    setLoadingPianos(true)
    apiFetch('/api/pianos/')
      .then(r => r.json())
      .then(data => { setPianos(data.results ?? data); setLoadingPianos(false) })
      .catch(() => setLoadingPianos(false))
  }, [])

  function togglePiano(id) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleAll() {
    if (selected.size === pianos.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(pianos.map(p => p.id)))
    }
  }

  async function handleApply() {
    if (selected.size === 0) return
    setApplying(true)
    setError(null)
    try {
      const res = await apiFetch(`/api/schedule-templates/${template.id}/apply_to_pianos/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ piano_ids: [...selected] }),
      })
      if (!res.ok) {
        const data = await res.json()
        setError(data.error ?? 'Failed to apply template.')
      } else {
        const data = await res.json()
        setSuccess(`Created ${data.created} schedule${data.created !== 1 ? 's' : ''}.`)
        onApplied()
      }
    } catch {
      setError('Network error — is Django running?')
    } finally {
      setApplying(false)
    }
  }

  // Group pianos by location for readability
  const byLocation = pianos.reduce((acc, p) => {
    const loc = p.location_name ?? 'Unknown'
    ;(acc[loc] = acc[loc] ?? []).push(p)
    return acc
  }, {})

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal apply-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>Apply Template to Pianos</h2>
            <p className="modal-subtitle">"{template.name}"</p>
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        {error && <div className="modal-error">{error}</div>}
        {success && <div className="modal-success">{success}</div>}

        <div className="apply-body">
          <div className="apply-select-all">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={selected.size === pianos.length && pianos.length > 0}
                onChange={toggleAll}
              />
              Select all ({pianos.length} pianos)
            </label>
            <span className="apply-count">{selected.size} selected</span>
          </div>

          <div className="piano-checklist">
            {loadingPianos ? (
              <div className="td-loading" style={{ justifyContent: 'center', padding: '1.5rem 0' }}>
                <span className="td-loading-inner"><span className="spinner" />Loading pianos…</span>
              </div>
            ) : null}
            {!loadingPianos && Object.entries(byLocation).map(([loc, lPianos]) => (
              <div key={loc} className="location-group">
                <div className="location-label">{loc}</div>
                {lPianos.map(p => (
                  <label key={p.id} className="checkbox-label piano-check-row">
                    <input
                      type="checkbox"
                      checked={selected.has(p.id)}
                      onChange={() => togglePiano(p.id)}
                    />
                    <span className="piano-check-name">{p.name}</span>
                    <span className="piano-check-meta">{p.brand} {p.model} · {p.piano_type}</span>
                  </label>
                ))}
              </div>
            ))}
            {!loadingPianos && pianos.length === 0 && (
              <p className="empty-note">No pianos found. Add pianos first.</p>
            )}
          </div>
        </div>

        <div className="modal-actions apply-actions">
          {success ? (
            <button className="btn-primary" onClick={onClose}>Done</button>
          ) : (
            <>
              <button className="btn-secondary" onClick={onClose}>Cancel</button>
              <button
                className="btn-primary"
                onClick={handleApply}
                disabled={selected.size === 0 || applying}
              >
                {applying ? 'Applying…' : `Apply to ${selected.size} Piano${selected.size !== 1 ? 's' : ''}`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
