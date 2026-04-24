import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import PianoFormModal from '../components/PianoFormModal'
import { apiFetch } from '../api'
import './PianosPage.css'

export default function PianosPage() {
  const [pianos,        setPianos]        = useState([])
  const [loading,       setLoading]       = useState(true)
  const [error,         setError]         = useState(null)
  const [modalOpen,     setModalOpen]     = useState(false)
  const [editingPiano,  setEditingPiano]  = useState(null)
  const [deactivateConfirm, setDeactivateConfirm] = useState(null)
  const [showInactive,  setShowInactive]  = useState(false)

  // Fetch the right list based on toggle
  const loadPianos = useCallback(() => {
    setLoading(true)
    const url = showInactive ? '/api/pianos/?active=false' : '/api/pianos/'
    apiFetch(url)
      .then(r => r.json())
      .then(data => { setPianos(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load pianos — is Django running?'); setLoading(false) })
  }, [showInactive])

  useEffect(() => { loadPianos() }, [loadPianos])

  function openCreate() {
    setEditingPiano(null)
    setModalOpen(true)
  }

  function openEdit(piano) {
    setEditingPiano(piano)
    setModalOpen(true)
  }

  function handleSaved() {
    setModalOpen(false)
    setEditingPiano(null)
    loadPianos()
  }

  // Soft-deactivate via DELETE (backend sets is_active=False, returns 204)
  async function handleDeactivate(piano) {
    try {
      const r = await apiFetch(`/api/pianos/${piano.id}/`, { method: 'DELETE' })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        setError(data.detail || data.error || 'Deactivate failed.')
        setDeactivateConfirm(null)
        return
      }
      setDeactivateConfirm(null)
      loadPianos()
    } catch {
      setError('Deactivate failed — network error.')
    }
  }

  // Reactivate via POST
  async function handleReactivate(piano) {
    try {
      const r = await apiFetch(`/api/pianos/${piano.id}/reactivate/`, { method: 'POST' })
      if (r.ok) loadPianos()
      else setError('Reactivate failed.')
    } catch {
      setError('Reactivate failed — network error.')
    }
  }

  const subtitle = showInactive
    ? `${pianos.length} inactive piano${pianos.length !== 1 ? 's' : ''}`
    : `${pianos.length} piano${pianos.length !== 1 ? 's' : ''} registered`

  return (
    <div className="pianos-page">
      <div className="page-header">
        <div>
          <h2>Pianos</h2>
          <p className="page-subtitle">{subtitle}</p>
        </div>
        <div className="header-actions">
          <button
            className={showInactive ? 'btn-secondary active' : 'btn-secondary'}
            onClick={() => { setError(null); setShowInactive(v => !v) }}
          >
            {showInactive ? '← Active Pianos' : 'View Inactive Pianos'}
          </button>
          {!showInactive && (
            <button className="btn-primary" onClick={openCreate}>+ Add Piano</button>
          )}
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="loading">Loading…</div>
      ) : pianos.length === 0 ? (
        <div className="empty-state">
          {showInactive ? (
            <p>No inactive pianos.</p>
          ) : (
            <>
              <p>No pianos yet.</p>
              <button className="btn-primary" onClick={openCreate}>Add your first piano</button>
            </>
          )}
        </div>
      ) : (
        <>
          {showInactive && (
            <div className="inactive-banner">
              Showing inactive pianos — these are hidden from active views and scheduling.
            </div>
          )}

          <div className="table-wrapper">
            <table className="pianos-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Brand</th>
                  <th>Model</th>
                  <th>Type</th>
                  <th>Location</th>
                  <th>Serial #</th>
                  <th>Year Built</th>
                  <th>Year Acquired</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pianos.map(piano => (
                  <tr key={piano.id} className={showInactive ? 'inactive-row' : ''}>
                    <td className="piano-name">
                      <div className="piano-name-cell">
                        {piano.profile_photo_url
                          ? <img src={piano.profile_photo_url} alt="" className="piano-thumb" />
                          : <div className="piano-thumb piano-thumb-placeholder"></div>
                        }
                        <Link to={`/pianos/${piano.id}`}>{piano.name}</Link>
                      </div>
                    </td>
                    <td>{piano.brand}</td>
                    <td>{piano.model || <span className="empty">—</span>}</td>
                    <td>
                      <span className={`badge type-${piano.piano_type.toLowerCase()}`}>
                        {piano.piano_type}
                      </span>
                    </td>
                    <td>{piano.location_name}</td>
                    <td>{piano.serial_number || <span className="empty">—</span>}</td>
                    <td>{piano.year_built    || <span className="empty">—</span>}</td>
                    <td>{piano.year_acquired || <span className="empty">—</span>}</td>
                    <td className="actions">
                      {showInactive ? (
                        <button className="btn-reactivate" onClick={() => handleReactivate(piano)}>
                          Reactivate
                        </button>
                      ) : (
                        <>
                          <button className="btn-edit" onClick={() => openEdit(piano)}>Edit</button>
                          <button
                            className="btn-delete"
                            onClick={() => { setError(null); setDeactivateConfirm(piano) }}
                          >
                            Deactivate
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {modalOpen && (
        <PianoFormModal
          piano={editingPiano}
          onClose={() => { setModalOpen(false); setEditingPiano(null) }}
          onSaved={handleSaved}
        />
      )}

      {deactivateConfirm && (
        <div className="modal-overlay" onClick={() => setDeactivateConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Deactivate Piano</h3>
            <p>
              Deactivate <strong>{deactivateConfirm.name}</strong>? It will no longer appear
              in active pianos, but all its history and work orders will be preserved.
            </p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setDeactivateConfirm(null)}>Cancel</button>
              <button className="btn-danger" onClick={() => handleDeactivate(deactivateConfirm)}>
                Deactivate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
