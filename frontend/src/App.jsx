import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import PianosPage from './pages/PianosPage'
import PianoProfilePage from './pages/PianoProfilePage'
import MaintenancePage from './pages/MaintenancePage'
import TechniciansPage from './pages/TechniciansPage'
import ReportsPage from './pages/ReportsPage'
import './App.css'

function Dashboard() {
  return (
    <div className="app-main">
      <h2>Welcome to Piano Maintainer</h2>
      <p>Track and manage piano maintenance records, schedules, and technicians.</p>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header className="app-header">
          <h1>Piano Maintainer</h1>
          <nav>
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/pianos">Pianos</NavLink>
            <NavLink to="/maintenance">Maintenance</NavLink>
            <NavLink to="/technicians">Technicians</NavLink>
            <NavLink to="/reports">Reports</NavLink>
            <NavLink to="/schedule">Schedule</NavLink>
          </nav>
        </header>

        <Routes>
          <Route path="/"              element={<Dashboard />} />
          <Route path="/pianos"        element={<PianosPage />} />
          <Route path="/pianos/:id"    element={<PianoProfilePage />} />
          <Route path="/maintenance"   element={<MaintenancePage />} />
          <Route path="/technicians"   element={<TechniciansPage />} />
          <Route path="/reports"       element={<ReportsPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default App
