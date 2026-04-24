import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import { useAuth } from '../AuthContext'
import TechnicianFormModal from '../components/TechnicianFormModal'
import TeamFormModal from '../components/TeamFormModal'
import './TechniciansPage.css'

export default function TechniciansPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('technicians')

  // ── Technician state ──
  const [techs, setTechs]             = useState([])
  const [techsLoading, setTechsLoading] = useState(true)
  const [techError, setTechError]     = useState(null)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [editingTech, setEditingTech] = useState(null)
  const [showInactive, setShowInactive] = useState(false)
  const [deactivateConfirm, setDeactivateConfirm] = useState(null)
  const [reactivateConfirm, setReactivateConfirm] = useState(null)
  const [deleteConfirm, setDeleteConfirm]         = useState(null)
  const [deleteError, setDeleteError]             = useState(null)

  // ── Team state ──
  const [teams, setTeams]           = useState([])
  const [teamsLoading, setTeamsLoading] = useState(true)
  const [teamError, setTeamError]   = useState(null)
  const [teamModal, setTeamModal]   = useState(undefined) // undefined=closed, null=create, obj=edit

  const loadTechs = useCallback(() => {
    setTechsLoading(true)
    apiFetch('/api/technicians/')
      .then(r => r.json())
      .then(data => { setTechs(data.results ?? data); setTechsLoading(false) })
      .catch(() => { setTechError('Failed to load technicians.'); setTechsLoading(false) })
  }, [])

  const loadTeams = useCallback(() => {
    setTeamsLoading(true)
    apiFetch('/api/teams/')
      .then(r => r.json())
      .then(data => { setTeams(data.results ?? data); setTeamsLoading(false) })
      .catch(() => { setTeamError('Failed to load teams.'); setTeamsLoading(false) })
  }, [])

  useEffect(() => { loadTechs(); loadTeams() }, [loadTechs, loadTeams])

  async function handleDeactivate(tech) {
    setTechError(null)
    try {
      const r = await apiFetch(`/api/technicians/${tech.id}/deactivate/`, { method: 'POST' })
      if (r.ok) {
        setDeactivateConfirm(null)
        loadTechs()
      } else {
        const data = await r.json().catch(() => ({}))
        setTechError(data.detail || `Deactivate failed (HTTP ${r.status}).`)
        setDeactivateConfirm(null)
      }
    } catch {
      setTechError('Deactivate failed — network error.')
      setDeactivateConfirm(null)
    }
  }

  async function handleReactivate(tech) {
    setTechError(null)
    try {
      const r = await apiFetch(`/api/technicians/${tech.id}/reactivate/`, { method: 'POST' })
      if (r.ok) {
        loadTechs()
      } else {
        const data = await r.json().catch(() => ({}))
        setTechError(data.detail || `Reactivate failed (HTTP ${r.status}).`)
      }
      setReactivateConfirm(null)
    } catch {
      setTechError('Reactivate failed — network error.')
      setReactivateConfirm(null)
    }
  }

  async function handleDelete(tech) {
    setDeleteError(null)
    try {
      const res = await apiFetch(`/api/technicians/${tech.id}/`, { method: 'DELETE' })
      if (res.status === 409) {
        const data = await res.json()
        setDeleteError(data.error || 'Cannot delete this technician.')
        setDeleteConfirm(null)
        return
      }
      if (res.ok || res.status === 204) {
        setTechs(prev => prev.filter(t => t.id !== tech.id))
        setDeleteConfirm(null)
      } else {
        setDeleteError('Delete failed.')
        setDeleteConfirm(null)
      }
    } catch {
      setDeleteError('Network error.')
      setDeleteConfirm(null)
    }
  }

  async function handleDeleteTeam(team) {
    if (!window.confirm(`Delete team "${team.name}"?`)) return
    await apiFetch(`/api/teams/${team.id}/`, { method: 'DELETE' })
    loadTeams()
  }

  const active   = techs.filter(t => t.is_active !== false)
  const inactive = techs.filter(t => t.is_active === false)
  const displayed = showInactive ? techs : active

  return (
    <div className="techs-page">
      {/* ── Page header ── */}
      <div className="page-header">
        <div>
          <h2>Technicians & Teams</h2>
          <p className="page-subtitle">
            {active.length} active{inactive.length > 0 ? `, ${inactive.length} inactive` : ''} · {teams.length} team{teams.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {activeTab === 'technicians' && inactive.length > 0 && (
            <label className="show-inactive-toggle">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={e => setShowInactive(e.target.checked)}
              />
              Show inactive
            </label>
          )}
          {user?.is_staff && activeTab === 'technicians' && (
            <button className="btn-primary" onClick={() => { setEditingTech(null); setAddModalOpen(true) }}>+ Add Technician</button>
          )}
          {user?.is_staff && activeTab === 'teams' && (
            <button className="btn-primary" onClick={() => setTeamModal(null)}>+ Create Team</button>
          )}
        </div>
      </div>

      {/* ── Errors (visible on both tabs) ── */}
      {techError  && <div className="page-error">{techError}</div>}
      {teamError  && <div className="page-error">{teamError}</div>}
      {deleteError && <div className="page-error">{deleteError}</div>}

      {/* ── Tabs ── */}
      <div className="tech-tabs">
        <button
          className={`tech-tab-btn${activeTab === 'technicians' ? ' tech-tab-btn--active' : ''}`}
          onClick={() => setActiveTab('technicians')}
        >
          Technicians
          <span className="tab-count">{techs.length}</span>
        </button>
        <button
          className={`tech-tab-btn${activeTab === 'teams' ? ' tech-tab-btn--active' : ''}`}
          onClick={() => setActiveTab('teams')}
        >
          Teams
          <span className="tab-count">{teams.length}</span>
        </button>
      </div>

      {/* ── Technicians tab ── */}
      {activeTab === 'technicians' && (
        <>
          {techsLoading ? (
            <div className="loading">Loading…</div>
          ) : displayed.length === 0 ? (
            <div className="empty-state">
              <p>No technicians yet.</p>
              {user?.is_staff && (
                <button className="btn-primary" onClick={() => { setEditingTech(null); setAddModalOpen(true) }}>
                  Add your first technician
                </button>
              )}
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="techs-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Specialization</th>
                    <th>Team</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Date Joined</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {displayed.map(t => {
                    const isMe = t.id === user?.id
                    return (
                      <tr key={t.id} className={`${t.is_active === false ? 'row-inactive' : ''}${isMe ? ' row-me' : ''}`}>
                        <td className="tech-name">
                          {t.full_name ?? `${t.first_name} ${t.last_name}`}
                          {isMe && <span className="you-badge">You</span>}
                        </td>
                        <td>{t.username}</td>
                        <td>{t.email || <span className="empty">—</span>}</td>
                        <td>{t.phone || <span className="empty">—</span>}</td>
                        <td>{t.specialization || <span className="empty">—</span>}</td>
                        <td>{t.team_name || <span className="empty">—</span>}</td>
                        <td>
                          {t.is_staff
                            ? <span className="badge badge-staff">Staff</span>
                            : <span className="badge badge-tech">Technician</span>}
                        </td>
                        <td>
                          {t.is_active !== false
                            ? <span className="badge badge-active">Active</span>
                            : <span className="badge badge-inactive">Inactive</span>}
                        </td>
                        <td>{t.date_joined ? t.date_joined.slice(0, 10) : <span className="empty">—</span>}</td>
                        <td className="actions">
                          <button className="btn-edit" onClick={() => { setEditingTech(t); setAddModalOpen(true) }}>
                            Edit
                          </button>
                          {t.is_active !== false ? (
                            user?.is_staff && t.id !== user?.id && (
                              <button className="btn-deactivate" onClick={() => setDeactivateConfirm(t)}>
                                Deactivate
                              </button>
                            )
                          ) : (
                            user?.is_staff && (
                              <button className="btn-reactivate" onClick={() => setReactivateConfirm(t)}>
                                Reactivate
                              </button>
                            )
                          )}
                          {user?.is_staff && t.id !== user?.id && (
                            <button className="btn-delete-row" onClick={() => { setDeleteError(null); setDeleteConfirm(t) }}>
                              Delete
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Teams tab ── */}
      {activeTab === 'teams' && (
        <>
          <div className="table-wrapper">
            <table className="techs-table">
              <thead>
                <tr>
                  <th>Team Name</th>
                  <th>Manager</th>
                  <th>Members</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {teamsLoading ? (
                  <tr><td colSpan={4} className="td-loading">Loading…</td></tr>
                ) : teams.length === 0 ? (
                  <tr><td colSpan={4} className="td-empty">No teams yet. Create one above.</td></tr>
                ) : teams.map(team => (
                  <tr key={team.id}>
                    <td style={{ fontWeight: 500 }}>{team.name}</td>
                    <td>{team.manager_name || <span className="empty">—</span>}</td>
                    <td>{techs.filter(t => t.team === team.id).length}</td>
                    <td className="actions">
                      {user?.is_staff && (
                        <>
                          <button className="btn-edit" onClick={() => setTeamModal(team)}>Edit</button>
                          <button className="btn-delete-row" onClick={() => handleDeleteTeam(team)}>Delete</button>
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

      {/* ── Modals ── */}
      {addModalOpen && (
        <TechnicianFormModal
          technician={editingTech}
          teams={teams}
          onClose={() => { setAddModalOpen(false); setEditingTech(null) }}
          onSaved={() => { setAddModalOpen(false); setEditingTech(null); loadTechs() }}
        />
      )}

      {teamModal !== undefined && (
        <TeamFormModal
          team={teamModal}
          techs={techs}
          onClose={() => setTeamModal(undefined)}
          onSaved={() => { setTeamModal(undefined); loadTeams() }}
        />
      )}

      {/* Deactivate confirm */}
      {deactivateConfirm && (
        <div className="modal-overlay" onClick={() => setDeactivateConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Deactivate Technician</h3>
            <p>Deactivate <strong>{deactivateConfirm.full_name ?? `${deactivateConfirm.first_name} ${deactivateConfirm.last_name}`}</strong>? They will no longer be able to sign in.</p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setDeactivateConfirm(null)}>Cancel</button>
              <button className="btn-danger" onClick={() => handleDeactivate(deactivateConfirm)}>Deactivate</button>
            </div>
          </div>
        </div>
      )}

      {/* Reactivate confirm */}
      {reactivateConfirm && (
        <div className="modal-overlay" onClick={() => setReactivateConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Reactivate Technician</h3>
            <p>Reactivate <strong>{reactivateConfirm.full_name ?? `${reactivateConfirm.first_name} ${reactivateConfirm.last_name}`}</strong>? They will regain access to sign in.</p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setReactivateConfirm(null)}>Cancel</button>
              <button className="btn-primary" onClick={() => handleReactivate(reactivateConfirm)}>Reactivate</button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Technician</h3>
            <p>Permanently delete <strong>{deleteConfirm.full_name ?? `${deleteConfirm.first_name} ${deleteConfirm.last_name}`}</strong>? This cannot be undone.</p>
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
