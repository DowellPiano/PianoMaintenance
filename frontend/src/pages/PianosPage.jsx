import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import PianoFormModal from '../components/PianoFormModal'
import { apiFetch } from '../api'
import './PianosPage.css'

export default function PianosPage() {
  const [pianos, setPianos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingPiano, setEditingPiano] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  const loadPianos = useCallback(() => {
    setLoading(true)
    apiFetch('/api/pianos/')
      .then(r => r.json())
      .then(data => { setPianos(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load pianos — is Django running?'); setLoading(false) })
  }, [])

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

  async function handleDelete(piano) {
    try {
      await apiFetch(`/api/pianos/${piano.id}/`, { method: 'DELETE' })
      setDeleteConfirm(null)
      loadPianos()
    } catch {
      setError('Delete failed.')
    }
  }

  return (
    <div className="pianos-page">
      <div className="page-header">
        <div>
          <h2>Pianos</h2>
          <p className="page-subtitle">{pianos.length} piano{pianos.length !== 1 ? 's' : ''} registered</p>
        </div>
        <button className="btn-primary" onClick={openCreate}>+ Add Piano</button>
      </div>

      {error && <div className="page-error">{error}</div>}

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
            {loading ? (
              <tr>
                <td colSpan={9} className="td-loading">
                  <span className="td-loading-inner"><span className="spinner" />Loading pianos…</span>
                </td>
              </tr>
            ) : pianos.length === 0 ? (
              <tr>
                <td colSpan={9} className="td-empty">
                  No pianos yet.{' '}
                  <button className="btn-link" onClick={openCreate}>Add your first piano</button>
                </td>
              </tr>
            ) : (
              pianos.map(piano => (
                <tr key={piano.id}>
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
                    <button className="btn-edit" onClick={() => openEdit(piano)}>Edit</button>
                    <button className="btn-delete" onClick={() => setDeleteConfirm(piano)}>Delete</button>
                  </td>
                </tr>
            )))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <PianoFormModal
          piano={editingPiano}
          onClose={() => { setModalOpen(false); setEditingPiano(null) }}
          onSaved={handleSaved}
        />
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Piano</h3>
            <p>Are you sure you want to delete <strong>{deleteConfirm.name}</strong>?</p>
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
