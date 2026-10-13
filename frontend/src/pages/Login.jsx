import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Button, ErrorBox, Field, Input } from '../components/ui'
import { errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { LANGUAGES, t, useLang } from '../lib/i18n'

export default function Login() {
  const { user, login } = useAuth()
  const { lang, setLang } = useLang()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(identifier.trim(), password)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-brand-50 via-white to-brand-100/50 p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-black/10 bg-white p-7 shadow-sm">
        <div className="-mt-2 mb-2 flex justify-end gap-1 text-xs">
          {LANGUAGES.map((l) => (
            <button
              key={l.value}
              type="button"
              onClick={() => setLang(l.value)}
              className={lang === l.value ? 'rounded px-2 py-0.5 font-semibold text-brand-700' : 'rounded px-2 py-0.5 text-gray-500 hover:bg-gray-100'}
            >
              {l.label}
            </button>
          ))}
        </div>
        <div className="mb-6 text-center">
          <div className="bg-brand-gradient mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl font-bold text-white">KVP</div>
          <h1 className="text-lg font-semibold text-gray-900">{t('Kishori Vikas Programme')}</h1>
          <p className="text-sm text-gray-500">{t('Volunteer / Stakeholder login')}</p>
        </div>
        <ErrorBox message={error} />
        <div className="space-y-3">
          <Field label={t('Mobile number or email')}>
            <Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" required />
          </Field>
          <Field label={t('Password')}>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </Field>
          <Button type="submit" className="w-full" busy={busy}>
            {t('Log in')}
          </Button>
        </div>
      </form>
    </div>
  )
}
