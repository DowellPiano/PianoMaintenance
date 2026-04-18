import { createContext, useContext, useState } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('authToken'))
  const [user,  setUser]  = useState(() => {
    try { return JSON.parse(localStorage.getItem('authUser')) } catch { return null }
  })

  async function login(username, password) {
    const res = await fetch('/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.error ?? 'Invalid username or password.')
    }
    const data = await res.json()
    localStorage.setItem('authToken', data.token)
    localStorage.setItem('authUser',  JSON.stringify(data.user))
    setToken(data.token)
    setUser(data.user)
  }

  function logout() {
    // Fire-and-forget: invalidate token on server
    if (token) {
      fetch('/api/auth/logout/', {
        method: 'POST',
        headers: { Authorization: `Token ${token}` },
      }).catch(() => {})
    }
    localStorage.removeItem('authToken')
    localStorage.removeItem('authUser')
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ token, user, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
