import { BrowserRouter, Routes, Route, NavLink, Navigate, Outlet } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import PianosPage from './pages/PianosPage'
import PianoProfilePage from './pages/PianoProfilePage'
import LocationsPage from './pages/LocationsPage'
import LocationProfilePage from './pages/LocationProfilePage'
import MaintenancePage from './pages/MaintenancePage'
import SchedulePage from './pages/SchedulePage'
import LoginPage from './pages/LoginPage'
import WorkOrdersPage from './pages/WorkOrdersPage'
import DashboardPage from './pages/DashboardPage'
import './App.css'

// Shared chrome (header + nav) for all authenticated pages.
// <Outlet /> is where React Router renders the matched child route.
function AppShell() {
  const { user, logout } = useAuth()

  return (
    <div className="app">
      <header className="app-header">
        <h1>Piano Maintainer</h1>
        <nav>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/pianos">Pianos</NavLink>
          <NavLink to="/locations">Locations</NavLink>
          <NavLink to="/work-orders">Work Orders</NavLink>
          <NavLink to="/maintenance">Maintenance</NavLink>
          <NavLink to="/schedule">Schedule</NavLink>
        </nav>
        <div className="header-user">
          <span className="header-username">
            {user?.first_name || user?.username}
          </span>
          <button className="btn-logout" onClick={logout}>Sign Out</button>
        </div>
      </header>

      <Outlet />
    </div>
  )
}

// Redirects unauthenticated visitors to /login.
function RequireAuth() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<LoginPage />} />

          {/* Auth gate — renders nothing itself, just checks the token */}
          <Route element={<RequireAuth />}>
            {/* App chrome wraps every protected page */}
            <Route element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route path="pianos"        element={<PianosPage />} />
              <Route path="pianos/:id"    element={<PianoProfilePage />} />
              <Route path="locations"     element={<LocationsPage />} />
              <Route path="locations/:id" element={<LocationProfilePage />} />
              <Route path="work-orders"   element={<WorkOrdersPage />} />
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
