import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api'
import './MaintenanceRequestsPage.css'

const STATUS_STYLE = {
  'New':      { background: '#fef2f2', color: '#b91c1c' },
  'Assigned': { background: '#fffbeb', color: '#b45309' },
  'Resolved': { background: '#f0fdf4', color: '#166534' },
}

export default function MaintenanceRequestsPage() {
  const navigate = useNavigate()
  const [requests, setRequests]       = useState([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [assigning, setAssigning]     = useState(null)  // id being assigned

  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (statusFilter) params.set('status', statusFilter)
    apiFetch(`/api/maintenance-requests/?${params}`)
      .then(r => r.json())
      .then(data => { setRequests(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load requests.'); setLoading(false) })
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  async function handleAssign(req) {
    setAssigning(req.id)
    try {
      const res = await apiFetch(`/api/maintenance-requests/${req.id}/assign/`, { method: 'POST' })
      if (!res.ok) {
        const data = await res.json()
        setError(data.error || 'Assign failed.')
      } else {
        load()
      }
    } catch {
      setError('Network error.')
    } finally {
      setAssigning(null)
    }
  }

  return (
    <div className="requests-page">
      <div className="page-header">
        <div>
          <h2>Maintenance Requests</h2>
          <p className="page-subtitle">{requests.length} request{requests.length !== 1 ? 's' : ''}</p>
        </div>
        <select
          className="status-filter"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="New">New</option>
          <option value="Assigned">Assigned</option>
          <option value="Resolved">Resolved</option>
        </select>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="table-wrapper">
        <table className="requests-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Piano</th>
              <th>Location</th>
              <th>Reported By</th>
              <th>Issue</th>
              <th>Status</th>
              <th>Date</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="td-loading">Loading…</td></tr>
            ) : requests.length === 0 ? (
              <tr>
                <td colSpan={8} className="td-empty">
                  {statusFilter ? `No ${statusFilter.toLowerCase()} requests.` : 'No maintenance requests.'}
                </td>
              </tr>
            ) : requests.map(req => (
              <tr key={req.id}>
                <td className="req-id">#{req.id}</td>
                <td className="req-piano">{req.piano_name}</td>
                <td>{req.piano_location || <span className="empty">—</span>}</td>
                <td>
                  <div className="reporter-name">{req.reported_by_name || <span className="empty">—</span>}</div>
                  {req.reported_by_email && (
                    <div className="reporter-email">{req.reported_by_email}</div>
                  )}
                </td>
                <td className="req-issue" title={req.issue_description}>
                  {req.issue_description.length > 70
                    ? req.issue_description.slice(0, 70) + '…'
                    : req.issue_description}
                </td>
                <td>
                  <span className="badge" style={STATUS_STYLE[req.status]}>{req.status}</span>
                </td>
                <td className="req-date">{req.created_at?.slice(0, 10)}</td>
                <td className="actions">
                  {req.status === 'New' && (
                    <button
                      className="btn-assign"
                      onClick={() => handleAssign(req)}
                      disabled={assigning === req.id}
                    >
                      {assigning === req.id ? 'Assigning…' : 'Assign → WO'}
                    </button>
                  )}
                  {req.status === 'Assigned' && req.work_order && (
                    <button
                      className="btn-view-wo"
                      onClick={() => navigate('/work-orders')}
                    >
                      View Work Order
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
