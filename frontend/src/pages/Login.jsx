import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import logo from '../assets/SEDT_logo.png'
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
    <div className="relative flex min-h-full items-center justify-center overflow-hidden bg-gradient-to-br from-brand-50 via-white to-brand-100/60 p-4 sm:p-8">
      <div aria-hidden="true" className="pointer-events-none absolute -left-32 -top-32 h-80 w-80 rounded-full bg-brand-500/10 blur-3xl" />
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-40 -right-32 h-96 w-96 rounded-full bg-brand-700/10 blur-3xl" />
      <form onSubmit={submit} className="relative w-full max-w-sm rounded-2xl border border-white/80 bg-white/95 p-7 shadow-xl shadow-brand-900/10 backdrop-blur sm:p-8">
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
        <div className="mb-7 text-center">
          <img src={logo} alt="SEDT logo" className="mx-auto mb-4 h-24 w-24 object-contain" />
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">{t('Kishori Vikas Programme')}</h1>
          <p className="mt-1 text-sm text-gray-500">{t('Volunteer / Stakeholder login')}</p>
        </div>
        <ErrorBox message={error} />
        <div className="space-y-3">
          <Field label={t('Mobile number or email')}>
            <Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" required />
          </Field>
          <Field label={t('Password')}>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </Field>
          <Button type="submit" className="mt-1 w-full py-2.5 shadow-md shadow-brand-800/15" busy={busy}>
            {t('Log in')}
          </Button>
        </div>
        <p className="mt-6 text-center text-xs text-gray-500">
          {t('A programme of')}{' '}
          <Link to="/home" className="font-medium text-brand-700 hover:underline">
            {t('Socio-Economic Development Trust')}
          </Link>
        </p>
      </form>
    </div>
  )
}
