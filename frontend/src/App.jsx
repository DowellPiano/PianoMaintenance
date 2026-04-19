import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate, Outlet } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import { apiFetch } from './api'
import AlertDrawer from './components/AlertDrawer'
import PianosPage from './pages/PianosPage'
import PianoProfilePage from './pages/PianoProfilePage'
import LocationsPage from './pages/LocationsPage'
import LocationProfilePage from './pages/LocationProfilePage'
import MaintenancePage from './pages/MaintenancePage'
import SchedulePage from './pages/SchedulePage'
import LoginPage from './pages/LoginPage'
import WorkOrdersPage from './pages/WorkOrdersPage'
import DashboardPage from './pages/DashboardPage'
import PartsPage from './pages/PartsPage'
import TechniciansPage from './pages/TechniciansPage'
import './App.css'

// Shared chrome (header + nav) for all authenticated pages.
function AppShell() {
  const { user, logout } = useAuth()
  const [alertCount, setAlertCount] = useState(0)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Poll for unacknowledged alert count
  useEffect(() => {
    function fetchAlerts() {
      apiFetch('/api/alerts/unread-count/')
        .then(r => r.json())
        .then(data => setAlertCount(data.total ?? 0))
        .catch(() => {})
    }
    fetchAlerts()
    const id = setInterval(fetchAlerts, 60_000)
    window.addEventListener('alerts-changed', fetchAlerts)
    return () => {
      clearInterval(id)
      window.removeEventListener('alerts-changed', fetchAlerts)
    }
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Piano Maintainer</h1>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/pianos">Pianos</NavLink>
          <NavLink to="/locations">Locations</NavLink>
          <NavLink to="/work-orders">Work Orders</NavLink>
          <NavLink to="/parts">Parts</NavLink>
          {user?.is_staff && <NavLink to="/technicians">Technicians</NavLink>}
          <NavLink to="/maintenance">Maintenance</NavLink>
          <NavLink to="/schedule">Schedule</NavLink>
        </nav>
        <div className="header-right">
          <button
            className="bell-btn"
            onClick={() => setDrawerOpen(d => !d)}
            aria-label="Notifications"
          >
            🔔
            {alertCount > 0 && (
              <span className="bell-badge">{alertCount > 99 ? '99+' : alertCount}</span>
            )}
          </button>
          <div className="header-user">
            <span className="header-username">{user?.first_name || user?.username}</span>
            <button className="btn-logout" onClick={logout}>Sign Out</button>
          </div>
        </div>
      </header>

      {drawerOpen && <AlertDrawer onClose={() => setDrawerOpen(false)} />}

      <Outlet />
    </div>
  )
}

// Redirects unauthenticated visitors to /login.
function RequireAuth() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />
}

function RedirectIfAuthed() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Navigate to="/" replace /> : <Outlet />
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public — redirect to / if already logged in */}
          <Route element={<RedirectIfAuthed />}>
            <Route path="/login" element={<LoginPage />} />
          </Route>

          {/* Auth gate */}
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route path="pianos"        element={<PianosPage />} />
              <Route path="pianos/:id"    element={<PianoProfilePage />} />
              <Route path="locations"     element={<LocationsPage />} />
              <Route path="locations/:id" element={<LocationProfilePage />} />
              <Route path="work-orders"   element={<WorkOrdersPage />} />
              <Route path="parts"         element={<PartsPage />} />
              <Route path="technicians"   element={<TechniciansPage />} />
              <Route path="maintenance"   element={<MaintenancePage />} />
              <Route path="schedule"      element={<SchedulePage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
