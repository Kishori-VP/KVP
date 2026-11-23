import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import api, { getToken, setToken } from './api'
import { invalidateRefData } from './hooks'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(getToken()))

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    invalidateRefData()
  }, [])

  useEffect(() => {
    const onLogout = () => {
      setUser(null)
      invalidateRefData()
    }
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
    invalidateRefData()
    const r = await api.post('/auth/login', { identifier, password })
    setToken(r.data.access_token)
    setUser(r.data.user)
    return r.data.user
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

/** Roles that may open the media library ("stakeholder" / "admin" are legacy names). */
export const MEDIA_ROLES = ['super_admin', 'stakeholder', 'admin_1', 'admin']

export function useAuth() {
  return useContext(AuthContext)
}
