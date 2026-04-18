import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import LocationFormModal from '../components/LocationFormModal'
import PianoFormModal from '../components/PianoFormModal'
import './LocationProfilePage.css'

const TYPE_CLASS = { Grand: 'grand', Upright: 'upright', Digital: 'digital' }

export default function LocationProfilePage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [data, setData]             = useState(null)   // { location, pianos }
  const [loading, setLoading]       = useState(true)
  const [error, setError]           = useState(null)
  const [editLocOpen, setEditLocOpen]     = useState(false)
  const [editPiano, setEditPiano]         = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)
  const [deleteError, setDeleteError]     = useState(null)

  function loadProfile() {
    setLoading(true)
    fetch(`/api/locations/${id}/profile/`)
      .then(r => { if (!r.ok) throw new Error('Not found'); return r.json() })
      .then(d  => { setData(d); setLoading(false) })
      .catch(()  => { setError('Could not load location.'); setLoading(false) })
  }

  useEffect(() => { loadProfile() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleLocationSaved() {
    setEditLocOpen(false)
    loadProfile()
  }

  function handlePianoSaved() {
    setEditPiano(null)
    loadProfile()
  }

  async function handleDeletePiano(piano) {
    setDeleteError(null)
    try {
      const res = await fetch(`/api/pianos/${piano.id}/`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed.')
      setDeleteConfirm(null)
      loadProfile()
    } catch (err) {
      setDeleteError(err.message)
    }
  }

  if (loading) return <div className="lp-loading">Loading…</div>
  if (error)   return <div className="lp-error">{error} <Link to="/locations">← Back</Link></div>

  const { location, pianos } = data

  return (
    <div className="lp-page">

      {/* ── Back ── */}
      <Link to="/locations" className="lp-back">← All Locations</Link>

      {/* ── Hero ── */}
      <div className="lp-hero">
        <div className="lp-hero-icon">📍</div>
        <div className="lp-hero-info">
          <h2 className="lp-name">{location.name}</h2>
          {location.building && <p className="lp-building">{location.building}</p>}
          {location.address  && <p className="lp-address">{location.address}</p>}
        </div>
        <div className="lp-hero-stats">
          <div className="lp-stat">
            <span className="lp-stat-value">{pianos.length}</span>
            <span className="lp-stat-label">Piano{pianos.length !== 1 ? 's' : ''}</span>
          </div>
        </div>
        <button className="btn-edit-hero" onClick={() => setEditLocOpen(true)}>Edit Location</button>
      </div>

      {/* ── Pianos grid ── */}
      <div className="lp-section">
        <div className="lp-section-header">
          <h3>Pianos at this Location</h3>
        </div>

        {pianos.length === 0 ? (
          <div className="lp-empty">No pianos assigned to this location yet.</div>
        ) : (
          <div className="lp-piano-grid">
            {pianos.map(piano => (
              <div key={piano.id} className="lp-piano-card">
                {/* Photo or placeholder */}
                <div className="lp-piano-photo">
                  {piano.profile_photo_url
                    ? <img src={piano.profile_photo_url} alt={piano.name} />
                    : <div className="lp-piano-photo-placeholder">🎹</div>
                  }
                </div>

                <div className="lp-piano-body">
                  <div className="lp-piano-top">
                    <Link to={`/pianos/${piano.id}`} className="lp-piano-name">
                      {piano.name}
                    </Link>
                    <span className={`badge type-${TYPE_CLASS[piano.piano_type] || 'other'}`}>
                      {piano.piano_type}
                    </span>
                  </div>

                  <p className="lp-piano-meta">
                    {piano.brand}{piano.model ? ` ${piano.model}` : ''}
                  </p>

                  {piano.serial_number && (
                    <p className="lp-piano-serial">S/N: {piano.serial_number}</p>
                  )}

                  <div className="lp-piano-actions">
                    <Link to={`/pianos/${piano.id}`} className="btn-view">View Profile</Link>
                    <button className="btn-edit-sm" onClick={() => setEditPiano(piano)}>Edit</button>
                    <button className="btn-delete-sm" onClick={() => { setDeleteError(null); setDeleteConfirm(piano) }}>Delete</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Modals ── */}
      {editLocOpen && (
        <LocationFormModal
          location={location}
          onClose={() => setEditLocOpen(false)}
          onSaved={handleLocationSaved}
        />
      )}

      {editPiano && (
        <PianoFormModal
          piano={editPiano}
          onClose={() => setEditPiano(null)}
          onSaved={handlePianoSaved}
        />
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Piano</h3>
            <p>Are you sure you want to delete <strong>{deleteConfirm.name}</strong>? This cannot be undone.</p>
            {deleteError && <div className="modal-error">{deleteError}</div>}
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(null)}>Cancel</button>
              <button className="btn-danger" onClick={() => handleDeletePiano(deleteConfirm)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
