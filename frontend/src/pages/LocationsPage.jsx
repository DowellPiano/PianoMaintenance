import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import LocationFormModal from '../components/LocationFormModal'
import './LocationsPage.css'

export default function LocationsPage() {
  const [locations, setLocations]     = useState([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [modalOpen, setModalOpen]     = useState(false)
  const [editing, setEditing]         = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)
  const [deleteError, setDeleteError] = useState(null)

  const loadLocations = useCallback(() => {
    setLoading(true)
    fetch('/api/locations/')
      .then(r => r.json())
      .then(data => { setLocations(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load locations — is Django running?'); setLoading(false) })
  }, [])

  useEffect(() => { loadLocations() }, [loadLocations])

  function openCreate() { setEditing(null); setModalOpen(true) }
  function openEdit(loc) { setEditing(loc); setModalOpen(true) }

  function handleSaved() {
    setModalOpen(false)
    setEditing(null)
    loadLocations()
  }

  async function handleDelete(loc) {
    setDeleteError(null)
    try {
      const res = await fetch(`/api/locations/${loc.id}/`, { method: 'DELETE' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Delete failed — this location may have pianos assigned to it.')
      }
      setDeleteConfirm(null)
      loadLocations()
    } catch (err) {
      setDeleteError(err.message)
    }
  }

  return (
    <div className="locations-page">
      <div className="page-header">
        <div>
          <h2>Locations</h2>
          <p className="page-subtitle">
            {locations.length} location{locations.length !== 1 ? 's' : ''} registered
          </p>
        </div>
        <button className="btn-primary" onClick={openCreate}>+ Add Location</button>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <div className="loading">Loading…</div>
      ) : locations.length === 0 ? (
        <div className="empty-state">
          <p>No locations yet.</p>
          <button className="btn-primary" onClick={openCreate}>Add your first location</button>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="locations-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Building</th>
                <th>Address</th>
                <th>Pianos</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {locations.map(loc => (
                <tr key={loc.id}>
                  <td className="loc-name">
                    <Link to={`/locations/${loc.id}`}>{loc.name}</Link>
                  </td>
                  <td>{loc.building || <span className="empty">—</span>}</td>
                  <td className="loc-address">{loc.address || <span className="empty">—</span>}</td>
                  <td>
                    <span className="piano-pill">{loc.piano_count ?? 0}</span>
                  </td>
                  <td className="actions">
                    <button className="btn-edit" onClick={() => openEdit(loc)}>Edit</button>
                    <button className="btn-delete" onClick={() => { setDeleteError(null); setDeleteConfirm(loc) }}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modalOpen && (
        <LocationFormModal
          location={editing}
          onClose={() => { setModalOpen(false); setEditing(null) }}
          onSaved={handleSaved}
        />
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Location</h3>
            <p>
              Are you sure you want to delete <strong>{deleteConfirm.name}</strong>?
              {deleteConfirm.piano_count > 0 && (
                <span className="warn-text">
                  {' '}This location has {deleteConfirm.piano_count} piano{deleteConfirm.piano_count !== 1 ? 's' : ''} — you must reassign or delete them first.
                </span>
              )}
            </p>
            {deleteError && <div className="modal-error" style={{ marginTop: 8 }}>{deleteError}</div>}
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setDeleteConfirm(null)}>Cancel</button>
              <button className="btn-danger" onClick={() => handleDelete(deleteConfirm)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
