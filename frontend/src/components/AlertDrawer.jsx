import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api'
import './AlertDrawer.css'

export default function AlertDrawer({ onClose }) {
  const [alerts,   setAlerts]   = useState([])
  const [loading,  setLoading]  = useState(true)
  const [ackingAll, setAckingAll] = useState(false)

  const load = useCallback(() => {
    apiFetch('/api/alerts/?acknowledged=false')
      .then(r => r.json())
      .then(data => { setAlerts(data.results ?? data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  async function acknowledge(id) {
    await apiFetch(`/api/alerts/${id}/acknowledge/`, { method: 'POST' })
    setAlerts(prev => prev.filter(a => a.id !== id))
    window.dispatchEvent(new CustomEvent('alerts-changed'))
  }

  async function acknowledgeAll() {
    setAckingAll(true)
    await Promise.all(alerts.map(a => apiFetch(`/api/alerts/${a.id}/acknowledge/`, { method: 'POST' })))
    setAlerts([])
    setAckingAll(false)
    window.dispatchEvent(new CustomEvent('alerts-changed'))
  }

  const overdue = alerts.filter(a => a.alert_type === 'OVERDUE')
  const dueSoon = alerts.filter(a => a.alert_type === 'DUE_SOON')

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="alert-drawer">
        <div className="drawer-header">
          <h3>Notifications</h3>
          <div className="drawer-header-actions">
            {alerts.length > 0 && (
              <button className="btn-text" onClick={acknowledgeAll} disabled={ackingAll}>
                {ackingAll ? 'Clearing…' : 'Acknowledge All'}
              </button>
            )}
            <button className="drawer-close" onClick={onClose}>×</button>
          </div>
        </div>

        {loading ? (
          <div className="drawer-loading">Loading…</div>
        ) : alerts.length === 0 ? (
          <div className="drawer-empty">
            <span className="drawer-empty-icon">—</span>
            <p>All caught up!</p>
            <p className="drawer-empty-sub">No unacknowledged alerts.</p>
          </div>
        ) : (
          <div className="drawer-sections">
            {overdue.length > 0 && (
              <section>
                <h4 className="drawer-section-title overdue-title">Overdue</h4>
                {overdue.map(a => (
                  <AlertCard key={a.id} alert={a} onAck={() => acknowledge(a.id)} />
                ))}
              </section>
            )}
            {dueSoon.length > 0 && (
              <section>
                <h4 className="drawer-section-title due-soon-title">Due Soon</h4>
                {dueSoon.map(a => (
                  <AlertCard key={a.id} alert={a} onAck={() => acknowledge(a.id)} />
                ))}
              </section>
            )}
          </div>
        )}
      </div>
    </>
  )
}

function AlertCard({ alert, onAck }) {
  return (
    <div className="alert-card">
      <div className="alert-card-body">
        <p className="alert-piano">{alert.piano_name}</p>
        {alert.piano_location && <p className="alert-location">{alert.piano_location}</p>}
        <p className="alert-meta">
          Due: {alert.due_date}
          {alert.priority && ` · ${alert.priority}`}
        </p>
      </div>
      <button className="btn-ack" onClick={onAck} title="Acknowledge">✓</button>
    </div>
  )
}
