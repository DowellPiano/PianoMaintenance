import { useState, useEffect } from 'react'
import { apiFetch } from '../api'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import './DashboardPage.css'

const PRIORITY_STYLE = {
  Urgent: { background: '#fef2f2', color: '#b91c1c' },
  High:   { background: '#fff7ed', color: '#c2410c' },
  Normal: { background: '#eff6ff', color: '#1d4ed8' },
  Low:    { background: '#f3f4f6', color: '#6b7280' },
}

const STATUS_STYLE = {
  'Open':        { background: '#eff6ff', color: '#1d4ed8' },
  'In Progress': { background: '#fffbeb', color: '#b45309' },
}

const KPI_CONFIG = [
  { key: 'open',                label: 'Open',               accent: '#3b82f6' },
  { key: 'in_progress',         label: 'In Progress',        accent: '#f59e0b' },
  { key: 'overdue',             label: 'Overdue',            accent: '#ef4444' },
  { key: 'due_soon',            label: 'Due Soon',           accent: '#eab308' },
  { key: 'completed_this_month', label: 'Completed This Month', accent: '#22c55e' },
]

export default function DashboardPage() {
  const [stats,      setStats]      = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState(null)
  const [editingWO,  setEditingWO]  = useState(null)   // full WO object for modal
  const [woLoading,  setWoLoading]  = useState(null)   // id currently being fetched

  function loadStats() {
    apiFetch('/api/dashboard/')
      .then(r => r.json())
      .then(data => { setStats(data); setLoading(false) })
      .catch(() => { setError('Failed to load dashboard.'); setLoading(false) })
  }

  useEffect(() => { loadStats() }, [])

  async function handleRowClick(wo) {
    setWoLoading(wo.id)
    try {
      const res  = await apiFetch(`/api/work-orders/${wo.id}/`)
      const data = await res.json()
      setEditingWO(data)
    } catch {
      setError('Failed to load work order.')
    } finally {
      setWoLoading(null)
    }
  }

  function handleSaved() {
    setEditingWO(null)
    setLoading(true)
    loadStats()
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <h2>Dashboard</h2>
      </div>

      {error && <div className="page-error">{error}</div>}

      {loading ? (
        <p className="dashboard-loading">Loading…</p>
      ) : stats && (
        <>
          <div className="kpi-row">
            {KPI_CONFIG.map(({ key, label, accent }) => (
              <div key={key} className="kpi-card" style={{ '--accent': accent }}>
                <div className="kpi-number">{stats[key] ?? 0}</div>
                <div className="kpi-label">{label}</div>
              </div>
            ))}
          </div>

          <div className="urgent-section">
            <h3>Active Work Orders</h3>
            {stats.urgent_open.length === 0 ? (
              <p className="no-urgent">No open or in-progress work orders.</p>
            ) : (
              <div className="table-wrapper">
                <table className="urgent-table">
                  <thead>
                    <tr>
                      <th>Piano</th>
                      <th>Location</th>
                      <th>Type</th>
                      <th>Priority</th>
                      <th>Status</th>
                      <th>Due Date</th>
                      <th>Assigned Tech</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.urgent_open.map(wo => (
                      <tr
                        key={wo.id}
                        className={`urgent-row${woLoading === wo.id ? ' urgent-row--loading' : ''}`}
                        onClick={() => handleRowClick(wo)}
                        title="Edit work order"
                      >
                        <td className="urgent-piano">{wo.piano_name}</td>
                        <td>{wo.piano_location}</td>
                        <td>{wo.order_type}</td>
                        <td>
                          <span className="badge" style={PRIORITY_STYLE[wo.priority]}>
                            {wo.priority}
                          </span>
                        </td>
                        <td>
                          <span className="badge" style={STATUS_STYLE[wo.status]}>
                            {wo.status}
                          </span>
                        </td>
                        <td>{wo.due_date || <span className="empty">—</span>}</td>
                                        <td>{wo.assigned_tech_name || <span className="empty">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {editingWO && (
        <WorkOrderFormModal
          workOrder={editingWO}
          onClose={() => setEditingWO(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
