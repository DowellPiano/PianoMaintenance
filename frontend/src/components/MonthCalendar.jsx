import './MonthCalendar.css'

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
]

function isoDate(y, m, d) {
  return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

export default function MonthCalendar({
  year, month, events, selectedDate,
  onPrev, onNext, onSelectDate,
}) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  // Build grid: 6 rows × 7 cols
  const firstDow = new Date(year, month, 1).getDay()   // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const daysInPrev  = new Date(year, month, 0).getDate()

  // Map events by date string → array
  const byDate = {}
  for (const ev of events) {
    ;(byDate[ev.date] = byDate[ev.date] ?? []).push(ev)
  }

  const cells = []
  // Leading blank days from previous month
  for (let i = firstDow - 1; i >= 0; i--) {
    cells.push({ day: daysInPrev - i, currentMonth: false, date: null })
  }
  // Current month days
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = isoDate(year, month, d)
    cells.push({ day: d, currentMonth: true, date: iso, evs: byDate[iso] ?? [] })
  }
  // Trailing days to fill last row
  let trailing = 1
  while (cells.length % 7 !== 0) {
    cells.push({ day: trailing++, currentMonth: false, date: null })
  }

  const rows = []
  for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7))

  return (
    <div className="month-cal">
      {/* Header */}
      <div className="cal-nav">
        <button className="cal-nav-btn" onClick={onPrev}>‹</button>
        <span className="cal-title">{MONTHS[month]} {year}</span>
        <button className="cal-nav-btn" onClick={onNext}>›</button>
      </div>

      <div className="cal-grid">
        {/* Day-of-week headers */}
        {DAYS.map(d => (
          <div key={d} className="cal-dow">{d}</div>
        ))}

        {/* Cells */}
        {rows.map((row, ri) =>
          row.map((cell, ci) => {
            if (!cell.currentMonth) {
              return <div key={`${ri}-${ci}`} className="cal-cell other-month" />
            }
            const cellDate = new Date(year, month, cell.day)
            const isToday    = cellDate.getTime() === today.getTime()
            const isSelected = cell.date === selectedDate
            const evs        = cell.evs ?? []
            // Show up to 3 event chips, then "+N more"
            const visible = evs.slice(0, 3)
            const overflow = evs.length - visible.length

            return (
              <div
                key={`${ri}-${ci}`}
                className={[
                  'cal-cell',
                  isToday    ? 'today'    : '',
                  isSelected ? 'selected' : '',
                ].join(' ')}
                onClick={() => onSelectDate(cell.date)}
              >
                <span className="cal-day-num">{cell.day}</span>
                <div className="cal-events">
                  {visible.map(ev => (
                    <div
                      key={ev.id}
                      className="cal-chip"
                      style={{ background: ev.color + '22', borderLeft: `3px solid ${ev.color}` }}
                      title={ev.title}
                    >
                      <span className="cal-chip-dot" style={{ background: ev.color }} />
                      <span className="cal-chip-text">{ev.title}</span>
                    </div>
                  ))}
                  {overflow > 0 && (
                    <div className="cal-overflow">+{overflow} more</div>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
