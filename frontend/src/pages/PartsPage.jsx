import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import PartFormModal from '../components/PartFormModal'
import './PartsPage.css'

export default function PartsPage() {
  const [parts, setParts]             = useState([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [modalOpen, setModalOpen]     = useState(false)
  const [editing, setEditing]         = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (lowStockOnly) params.set('needs_reorder', 'true')
    apiFetch(`/api/parts/?${params}`)
      .then(r => r.json())
      .then(data => { setParts(data.results ?? data); setLoading(false) })
      .catch(() => { setError('Failed to load parts.'); setLoading(false) })
  }, [lowStockOnly])

  useEffect(() => { load() }, [load])

  function openCreate() { setEditing(null); setModalOpen(true) }
  function openEdit(p)  { setEditing(p);    setModalOpen(true) }

  function handleSaved() { setModalOpen(false); setEditing(null); load() }

  async function handleDelete(p) {
    try {
      await apiFetch(`/api/parts/${p.id}/`, { method: 'DELETE' })
      setDeleteConfirm(null)
      load()
    } catch {
      setError('Delete failed.')
    }
  }

  return (
    <div className="parts-page">
      <div className="page-header">
        <div>
          <h2>Parts Inventory</h2>
          <p className="page-subtitle">{parts.length} part{parts.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="header-actions">
          <label className="low-stock-toggle">
            <input type="checkbox" checked={lowStockOnly} onChange={e => setLowStockOnly(e.target.checked)} />
            Show Low Stock Only
          </label>
          <button className="btn-primary" onClick={openCreate}>+ Add Part</button>
        </div>
      </div>

      {error && <div className="page-error">{error}</div>}

      <div className="table-wrapper">
        <table className="parts-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Part #</th>
              <th>Supplier</th>
              <th>Unit Cost</th>
              <th>Stock Qty</th>
              <th>Reorder At</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="td-loading">Loading…</td></tr>
            ) : parts.length === 0 ? (
              <tr>
                <td colSpan={8} className="td-empty">
                  {lowStockOnly ? 'No low-stock parts.' : 'No parts yet. '}
                  {!lowStockOnly && <button className="btn-link" onClick={openCreate}>Add your first part</button>}
                </td>
              </tr>
            ) : parts.map(p => (
              <tr key={p.id} className={p.needs_reorder ? 'row-low-stock' : ''}>
                <td className="part-name">{p.name}</td>
                <td>{p.part_number || <span className="empty">—</span>}</td>
                <td>{p.supplier    || <span className="empty">—</span>}</td>
                <td>{p.unit_cost != null ? `$${Number(p.unit_cost).toFixed(2)}` : <span className="empty">—</span>}</td>
                <td className={p.needs_reorder ? 'qty-low' : ''}>{p.stock_quantity}</td>
                <td>{p.reorder_threshold}</td>
                <td>
                  {p.needs_reorder
                    ? <span className="badge badge-low-stock">Low Stock</span>
                    : <span className="badge badge-ok">OK</span>}
                </td>
                <td className="actions">
                  <button className="btn-edit" onClick={() => openEdit(p)}>Edit</button>
                  <button className="btn-delete" onClick={() => setDeleteConfirm(p)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <PartFormModal
          part={editing}
          onClose={() => { setModalOpen(false); setEditing(null) }}
          onSaved={handleSaved}
        />
      )}

      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
            <h3>Delete Part</h3>
            <p>Delete <strong>{deleteConfirm.name}</strong>? This cannot be undone.</p>
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
