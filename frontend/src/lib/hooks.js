import { useCallback, useEffect, useRef, useState } from 'react'
import api, { clean, errorMessage } from './api'
import { getLang } from './i18n'

/**
 * GET a resource and re-fetch when the url or params change.
 * Returns { data, error, loading, reload, setData }.
 */
export function useFetch(url, params = null, { enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(Boolean(url && enabled))
  const key = JSON.stringify(params || {})
  const seq = useRef(0)

  const load = useCallback(async () => {
    if (!url || !enabled) return
    const mine = ++seq.current
    setLoading(true)
    setError(null)
    try {
      const r = await api.get(url, { params: clean(JSON.parse(key)) })
      if (mine === seq.current) setData(r.data)
    } catch (e) {
      if (mine === seq.current) setError(errorMessage(e))
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [url, key, enabled])

  useEffect(() => {
    load()
  }, [load])

  return { data, error, loading, reload: load, setData }
}

/** Run a mutating request with busy/error state. */
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = useCallback(async (fn) => {
    setBusy(true)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(errorMessage(e))
      throw e
    } finally {
      setBusy(false)
    }
  }, [])
  return { busy, error, setError, run }
}

/** Shared reference data (villages, talukas, lookups, volunteers), cached per page load. */
const cache = new Map()
export function useRefData(url, params) {
  const k = url + JSON.stringify(params || {})
  const [data, setData] = useState(cache.get(k) || null)
  useEffect(() => {
    let alive = true
    if (!cache.has(k)) {
      api.get(url, { params }).then((r) => {
        cache.set(k, r.data)
        if (alive) setData(r.data)
      }).catch(() => {})
    }
    return () => {
      alive = false
    }
  }, [k]) // eslint-disable-line react-hooks/exhaustive-deps
  return data
}

export function invalidateRefData() {
  cache.clear()
}

export const useVillages = () => useRefData('/villages') || []
export const useTalukas = () => useRefData('/talukas') || []
export const useVolunteers = () => useRefData('/volunteers') || []
export function useLookups(type) {
  return useRefData('/config/lookups', { type }) || []
}
export function lookupLabel(list, code) {
  const item = list.find((l) => l.code === code)
  if (!item) return code
  return getLang() === 'mr' && item.label_mr ? item.label_mr : item.label
}
