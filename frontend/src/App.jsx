import './App.css'

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Piano Maintainer</h1>
        <nav>
          <a href="#">Dashboard</a>
          <a href="#">Pianos</a>
          <a href="#">Maintenance</a>
          <a href="#">Schedule</a>
        </nav>
      </header>
      <main className="app-main">
        <h2>Welcome to Piano Maintainer</h2>
        <p>Track and manage piano maintenance records, schedules, and technicians.</p>
      </main>
    </div>
  )
}

export default App
