import { useState, useCallback } from 'react'
import './ReportsPage.css'

function todayStr() { return new Date().toISOString().slice(0, 10) }
function firstOfMonthStr() {
  const d = new Date()
  d.setDate(1)
  return d.toISOString().slice(0, 10)
}

function fmt(val, decimals = 2) {
  if (val == null || val === '') return '—'
  return Number(val).toFixed(decimals)
}

// ─── Technician Report ────────────────────────────────────────────────────────

function TechnicianReport({ dateFrom, dateTo }) {
  const [rows,    setRows]    = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  const runReport = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch ALL technicians — no ID param here
      const params = new URLSearchParams()
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo)   params.set('date_to',   dateTo)
      const r = await fetch(`/api/reports/technicians/?${params}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      // Accept array or { results: [...] } or { technicians: [...] }
      setRows(Array.isArray(data) ? data : data.results ?? data.technicians ?? [])
    } catch {
      setError('Failed to load technician report.')
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo])

  function handleExportCSV() {
    // Backend returns CSV with Content-Disposition: attachment — browser downloads it directly
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo)   params.set('date_to',   dateTo)
    window.open(`/api/reports/technicians/export_csv/?${params}`, '_blank')
  }

  return (
    <div className="report-section">
      <div className="report-controls">
        <button className="btn-primary rp-run-btn" onClick={runReport} disabled={loading}>
          {loading ? 'Running…' : 'Run Report'}
        </button>
        {rows !== null && (
          <button className="btn-export" onClick={handleExportCSV}>
            Export CSV
          </button>
        )}
      </div>

      {error && <div className="rp-error">{error}</div>}

      {rows === null && !loading && (
        <div className="rp-empty">Set your date range and click Run Report.</div>
      )}

      {rows !== null && (
        <>
          <div className="rp-summary">
            <span>{rows.length} technician{rows.length !== 1 ? 's' : ''}</span>
            <span className="rp-summary-total">
              Total hours: <strong>{fmt(rows.reduce((acc, r) => acc + Number(r.total_hours ?? 0), 0))}</strong>
            </span>
          </div>

          <div className="table-wrapper">
            <table className="rp-table">
              <thead>
                <tr>
                  <th>Technician</th>
                  <th>Work Orders</th>
                  <th>Total Hours</th>
                  <th>Avg Hours / WO</th>
                  <th>Pianos Serviced</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr><td colSpan={5} className="td-empty">No data for this period.</td></tr>
                ) : rows.map((r, i) => (
                  <tr key={r.technician_id ?? r.id ?? i}>
                    <td className="fw-medium">{r.full_name ?? r.name ?? `${r.first_name} ${r.last_name}`}</td>
                    <td>{r.work_orders_completed ?? r.work_order_count ?? '—'}</td>
                    <td>{fmt(r.total_hours)} h</td>
                    <td>{r.avg_hours_per_wo != null ? `${fmt(r.avg_hours_per_wo)} h` : '—'}</td>
                    <td>{r.pianos_serviced ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const TABS = [
  { key: 'technicians', label: 'Technician Report' },
]

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState('technicians')
  const [dateFrom,  setDateFrom]  = useState(firstOfMonthStr())
  const [dateTo,    setDateTo]    = useState(todayStr())

  return (
    <div className="rp-page">
      <div className="page-header">
        <h2>Reports</h2>
      </div>

      {/* Date range (global — applies to all reports) */}
      <div className="rp-date-row">
        <label>
          From
          <input
            type="date"
            value={dateFrom}
            max={dateTo}
            onChange={e => setDateFrom(e.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={dateTo}
            min={dateFrom}
            max={todayStr()}
            onChange={e => setDateTo(e.target.value)}
          />
        </label>
      </div>

      {/* Tab nav */}
      <div className="rp-tabs">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`rp-tab-btn${activeTab === t.key ? ' active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'technicians' && (
        <TechnicianReport dateFrom={dateFrom} dateTo={dateTo} />
      )}
    </div>
  )
}
