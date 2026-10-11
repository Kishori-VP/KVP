import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import api, { getToken, setToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(getToken()))

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('kvp:logout', onLogout)
    if (getToken()) {
      api
        .get('/auth/me')
        .then((r) => setUser(r.data))
        .catch(() => setToken(null))
        .finally(() => setLoading(false))
    }
    return () => window.removeEventListener('kvp:logout', onLogout)
  }, [])

  const login = async (identifier, password) => {
    const r = await api.post('/auth/login', { identifier, password })
    setToken(r.data.access_token)
    setUser(r.data.user)
    return r.data.user
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
