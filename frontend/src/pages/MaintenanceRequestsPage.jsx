import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import './MaintenanceRequestsPage.css'

const STATUS_STYLE = {
  'New':                { background: '#fef2f2', color: '#b91c1c' },
  'Pending Assignment': { background: '#eff6ff', color: '#1d4ed8' },
  'Assigned':           { background: '#f0fdf4', color: '#166534' },
  'Resolved':           { background: '#f3f4f6', color: '#6b7280' },
}

// A work order was created ("Assigned" on the model) but may or may not
// have a technician assigned to it yet.
function requestStatusLabel(req) {
  if (req.status !== 'Assigned') return req.status
  return req.wo_assigned_tech ? 'Assigned' : 'Pending Assignment'
}

const FILTERS = [
  { key: 'active',              label: 'Active' },
  { key: 'New',                 label: 'New' },
  { key: 'Pending Assignment',  label: 'Pending Assignment' },
  { key: 'Assigned',            label: 'Assigned' },
  { key: 'Resolved',            label: 'Resolved' },
  { key: 'all',                 label: 'All' },
]

function applyFilter(requests, filter) {
  if (filter === 'all')    return requests
  if (filter === 'active') return requests.filter(r => r.status !== 'Resolved')
  // Filter by computed display label so Pending Assignment / Assigned split works
  return requests.filter(r => requestStatusLabel(r) === filter)
}

export default function MaintenanceRequestsPage() {
  const [requests, setRequests]   = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)
  const [filter, setFilter]       = useState('active')   // default: hide Resolved
  const [assigning, setAssigning] = useState(null)       // request id being assigned
  const [editingWO, setEditingWO] = useState(null)       // full WO object for modal
  const [woLoading, setWoLoading] = useState(null)       // request id whose WO is loading

  const load = useCallback(() => {
    setLoading(true)
    // Always load all requests; filter client-side for instant switching
    apiFetch('/api/maintenance-requests/')
      .then(r => r.json())
      .then(data => { setRequests(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load requests.'); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  async function handleViewWO(req) {
    setWoLoading(req.id)
    try {
      const res  = await apiFetch(`/api/work-orders/${req.work_order}/`)
      const data = await res.json()
      setEditingWO(data)
    } catch {
      setError('Failed to load work order.')
    } finally {
      setWoLoading(null)
    }
  }

  async function handleAssign(req) {
    setAssigning(req.id)
    try {
      const res = await apiFetch(`/api/maintenance-requests/${req.id}/assign/`, { method: 'POST' })
      if (!res.ok) {
        const data = await res.json()
        setError(data.error || 'Assign failed.')
      } else {
        load()
        window.dispatchEvent(new CustomEvent('requests-badge-changed'))
      }
    } catch {
      setError('Network error.')
    } finally {
      setAssigning(null)
    }
  }

  const visible  = applyFilter(requests, filter)
  const activeCount = requests.filter(r => r.status !== 'Resolved').length

  return (
    <div className="requests-page">
      <div className="page-header">
        <div>
          <h2>Maintenance Requests</h2>
          <p className="page-subtitle">
            {activeCount} active · {requests.length} total
          </p>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="req-filter-bar">
        {FILTERS.map(({ key, label }) => (
          <button
            key={key}
            className={`req-filter-btn${filter === key ? ' active' : ''}`}
            onClick={() => setFilter(key)}
          >
            {label}
            {key !== 'all' && key !== 'active' && (
              <span className="req-filter-count">
                {applyFilter(requests, key).length}
              </span>
            )}
            {key === 'active' && (
              <span className="req-filter-count">{activeCount}</span>
            )}
          </button>
        ))}
      </div>

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
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={8} className="td-empty">
                  {requests.length === 0 ? 'No maintenance requests.' : `No ${filter === 'active' ? 'active' : filter.toLowerCase()} requests.`}
                </td>
              </tr>
            ) : visible.map(req => (
              <tr key={req.id} className={req.status === 'Resolved' ? 'row-resolved' : ''}>
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
                  {(() => {
                    const label = requestStatusLabel(req)
                    return (
                      <div>
                        <span className="badge" style={STATUS_STYLE[label]}>{label}</span>
                        {req.wo_assigned_tech && (
                          <div className="req-tech-name">👤 {req.wo_assigned_tech}</div>
                        )}
                      </div>
                    )
                  })()}
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
                      onClick={() => handleViewWO(req)}
                      disabled={woLoading === req.id}
                    >
                      {woLoading === req.id ? 'Loading…' : 'View Work Order'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editingWO && (
        <WorkOrderFormModal
          workOrder={editingWO}
          onClose={() => setEditingWO(null)}
          onSaved={() => { setEditingWO(null); load() }}
        />
      )}
    </div>
  )
}
