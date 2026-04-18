import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import { useAuth } from '../AuthContext'
import TechnicianFormModal from '../components/TechnicianFormModal'
import './TechniciansPage.css'

export default function TechniciansPage() {
  const { user } = useAuth()
  const [techs, setTechs]               = useState([])
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState(null)
  const [modalOpen, setModalOpen]       = useState(false)
  const [deactivateConfirm, setDeactivateConfirm] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    apiFetch('/api/technicians/')
      .then(r => r.json())
      .then(data => { setTechs(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load technicians.'); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  function handleSaved() { setModalOpen(false); load() }

  async function handleDeactivate(tech) {
    try {
      await apiFetch(`/api/technicians/${tech.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: false }),
      })
      setDeactivateConfirm(null)
      load()
    } catch {
      setError('Failed to deactivate technician.')
    }
  }

  return (
    <div className="techs-page">
      <div className="page-header">
        <div>
          <h2>Technicians</h2>
          <p className="page-subtitle">{techs.length} technician{techs.length !== 1 ? 's' : ''}</p>
        </div>
        {user?.is_staff && (
          <button className="btn-primary" onClick={() => setModalOpen(true)}>+ Add Technician</button>
        )}
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="table-wrapper">
        <table className="techs-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Username</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Date Joined</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} className="td-loading">Loading…</td></tr>
            ) : techs.length === 0 ? (
              <tr><td colSpan={7} className="td-empty">No technicians found.</td></tr>
            ) : techs.map(tech => {
              const isMe = tech.id === user?.id
              return (
                <tr key={tech.id} className={isMe ? 'row-me' : ''}>
                  <td className="tech-name">
                    {tech.full_name}
                    {isMe && <span className="you-badge">You</span>}
                  </td>
                  <td>{tech.username}</td>
                  <td>{tech.email || <span className="empty">—</span>}</td>
                  <td>
                    {tech.is_staff
                      ? <span className="badge badge-staff">Staff</span>
                      : <span className="badge badge-tech">Technician</span>}
                  </td>
                  <td>
                    {tech.is_active
                      ? <span className="badge badge-active">Active</span>
                      : <span className="badge badge-inactive">Inactive</span>}
                  </td>
                  <td>{tech.date_joined ? tech.date_joined.slice(0, 10) : <span className="empty">—</span>}</td>
                  <td className="actions">
                    {user?.is_staff && tech.is_active && tech.id !== user?.id && (
                      <button className="btn-deactivate" onClick={() => setDeactivateConfirm(tech)}>
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <TechnicianFormModal onClose={() => setModalOpen(false)} onSaved={handleSaved} />
      )}

      {deactivateConfirm && (
        <div className="modal-overlay" onClick={() => setDeactivateConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Deactivate Technician</h3>
            <p>
              Deactivate <strong>{deactivateConfirm.full_name}</strong>? They will no longer
              be able to sign in.
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
