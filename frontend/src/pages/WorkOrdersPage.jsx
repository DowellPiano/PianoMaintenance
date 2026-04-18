import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch } from '../api'
import WorkOrderFormModal from '../components/WorkOrderFormModal'
import LogEntryModal from '../components/LogEntryModal'
import './WorkOrdersPage.css'

const TODAY = new Date().toISOString().slice(0, 10)

const PRIORITY_STYLE = {
  Urgent: { background: '#fef2f2', color: '#b91c1c' },
  High:   { background: '#fff7ed', color: '#c2410c' },
  Normal: { background: '#eff6ff', color: '#1d4ed8' },
  Low:    { background: '#f3f4f6', color: '#6b7280' },
}

const STATUS_STYLE = {
  'Open':        { background: '#eff6ff', color: '#1d4ed8' },
  'In Progress': { background: '#fffbeb', color: '#b45309' },
  'Complete':    { background: '#f0fdf4', color: '#166534' },
  'Cancelled':   { background: '#f3f4f6', color: '#6b7280' },
}

function isOverdue(wo) {
  return wo.due_date && wo.due_date < TODAY &&
    wo.status !== 'Complete' && wo.status !== 'Cancelled'
}

export default function WorkOrdersPage() {
  const [workOrders, setWorkOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const debounceRef = useRef(null)

  // Modals
  const [editModal, setEditModal] = useState(null)   // null | workOrder object
  const [createOpen, setCreateOpen] = useState(false)
  const [logModal, setLogModal] = useState(null)     // null | workOrder object
  const [cancelConfirm, setCancelConfirm] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams({ ordering: '-due_date' })
    if (statusFilter)   params.set('status',   statusFilter)
    if (priorityFilter) params.set('priority', priorityFilter)
    if (searchQuery)    params.set('search',   searchQuery)

    apiFetch(`/api/work-orders/?${params}`)
      .then(r => r.json())
      .then(data => { setWorkOrders(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load work orders.'); setLoading(false) })
  }, [statusFilter, priorityFilter, searchQuery])

  useEffect(() => { load() }, [load])

  function handleSearchChange(e) {
    setSearchInput(e.target.value)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setSearchQuery(e.target.value), 300)
  }

  async function handleStart(wo) {
    try {
      await apiFetch(`/api/work-orders/${wo.id}/start/`, { method: 'POST' })
      load()
    } catch {
      setError('Failed to start work order.')
    }
  }

  async function handleCancel(wo) {
    try {
      await apiFetch(`/api/work-orders/${wo.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'Cancelled' }),
      })
      setCancelConfirm(null)
      load()
    } catch {
      setError('Failed to cancel work order.')
    }
  }

  function handleSaved() {
    setCreateOpen(false)
    setEditModal(null)
    load()
  }

  function handleLogged() {
    setLogModal(null)
    load()
  }

  const total = workOrders.length

  return (
    <div className="wo-page">
      <div className="page-header">
        <div>
          <h2>Work Orders</h2>
          <p className="page-subtitle">{total} work order{total !== 1 ? 's' : ''}</p>
        </div>
        <button className="btn-primary" onClick={() => setCreateOpen(true)}>+ New Work Order</button>
      </div>

      <div className="wo-filters">
        <input
          className="wo-search"
          type="search"
          placeholder="Search piano, description…"
          value={searchInput}
          onChange={handleSearchChange}
        />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="Open">Open</option>
          <option value="In Progress">In Progress</option>
          <option value="Complete">Complete</option>
          <option value="Cancelled">Cancelled</option>
        </select>
        <select value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}>
          <option value="">All Priorities</option>
          <option value="Urgent">Urgent</option>
          <option value="High">High</option>
          <option value="Normal">Normal</option>
          <option value="Low">Low</option>
        </select>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="table-wrapper">
        <table className="wo-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Piano</th>
              <th>Location</th>
              <th>Type</th>
              <th>Description</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Assigned Tech</th>
              <th>Due Date</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={10} className="td-loading">Loading…</td>
              </tr>
            ) : workOrders.length === 0 ? (
              <tr>
                <td colSpan={10} className="td-empty">No work orders found.</td>
              </tr>
            ) : (
              workOrders.map(wo => (
                <tr key={wo.id} className={isOverdue(wo) ? 'row-overdue' : ''}>
                  <td className="wo-id">#{wo.id}</td>
                  <td className="wo-piano">{wo.piano_name}</td>
                  <td>{wo.piano_location}</td>
                  <td>{wo.order_type}</td>
                  <td className="wo-desc" title={wo.description}>
                    {wo.description
                      ? wo.description.length > 60
                        ? wo.description.slice(0, 60) + '…'
                        : wo.description
                      : <span className="empty">—</span>}
                  </td>
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
                  <td>{wo.assigned_tech_name || <span className="empty">—</span>}</td>
                  <td className={isOverdue(wo) ? 'overdue-date' : ''}>
                    {wo.due_date || <span className="empty">—</span>}
                  </td>
                  <td className="actions">
                    <button className="btn-edit" onClick={() => setEditModal(wo)}>Edit</button>
                    {wo.status === 'Open' && (
                      <button className="btn-start" onClick={() => handleStart(wo)}>Start</button>
                    )}
                    {(wo.status === 'Open' || wo.status === 'In Progress') && (
                      <button className="btn-complete" onClick={() => setLogModal(wo)}>Complete</button>
                    )}
                    {(wo.status === 'Open' || wo.status === 'In Progress') && (
                      <button className="btn-cancel" onClick={() => setCancelConfirm(wo)}>Cancel</button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {(createOpen || editModal) && (
        <WorkOrderFormModal
          workOrder={editModal}
          onClose={() => { setCreateOpen(false); setEditModal(null) }}
          onSaved={handleSaved}
        />
      )}

      {logModal && (
        <LogEntryModal
          workOrder={logModal}
          onClose={() => setLogModal(null)}
          onSaved={handleLogged}
        />
      )}

      {cancelConfirm && (
        <div className="modal-overlay" onClick={() => setCancelConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Cancel Work Order</h3>
            <p>
              Cancel <strong>WO-{cancelConfirm.id}</strong> for{' '}
              <strong>{cancelConfirm.piano_name}</strong>?
            </p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setCancelConfirm(null)}>Keep Open</button>
              <button className="btn-danger" onClick={() => handleCancel(cancelConfirm)}>Yes, Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
