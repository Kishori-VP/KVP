import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { ArrowLeft, LogIn, Mail, Phone, Sparkles, UserPlus } from 'lucide-react'
import logo from '../assets/SEDT_logo.png'
import loginBg from '../assets/login_bg.webp'
import { Button, ErrorBox, Field, Input } from '../components/ui'
import { errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { LANGUAGES, t, useLang } from '../lib/i18n'

export default function Login() {
  const { user, login } = useAuth()
  const { lang, setLang } = useLang()
  const location = useLocation()

  const isSignupPath =
    location.pathname.includes('signup') || location.pathname.includes('register')
  const [overrideMode, setOverrideMode] = useState(null)
  const mode = overrideMode ?? (isSignupPath ? 'signup' : 'login')

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
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-y-auto p-4 sm:p-8">
      {/* Background Photograph */}
      <div
        className="fixed inset-0 bg-cover bg-center bg-no-repeat transition-all duration-700"
        style={{ backgroundImage: `url(${loginBg})` }}
        aria-hidden="true"
      />

      {/* Scrim Overlay with brand-tinted gradient for legibility & contrast */}
      <div
        className="fixed inset-0 bg-gradient-to-t from-black/85 via-slate-950/70 to-brand-950/75 backdrop-blur-[1.5px]"
        aria-hidden="true"
      />

      {/* Ambient background glows */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed -left-24 -top-24 h-80 w-80 rounded-full bg-brand-500/20 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none fixed -bottom-28 -right-24 h-96 w-96 rounded-full bg-teal-500/20 blur-3xl"
      />

      {/* Main Auth Card */}
      <div className="relative z-10 my-auto w-full max-w-md rounded-2xl border border-white/30 bg-white/95 p-6 shadow-2xl shadow-black/50 backdrop-blur-md sm:p-8">
        {/* Top bar with back to home & language toggle */}
        <div className="-mt-1 mb-4 flex items-center justify-between border-b border-gray-100 pb-3">
          <Link
            to="/home"
            className="flex items-center gap-1.5 text-xs font-medium text-gray-500 transition hover:text-brand-700"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>{t('Back to Home')}</span>
          </Link>
          <div className="flex items-center gap-1 text-xs">
            {LANGUAGES.map((l) => (
              <button
                key={l.value}
                type="button"
                onClick={() => setLang(l.value)}
                className={
                  lang === l.value
                    ? 'rounded-md bg-brand-50 px-2 py-0.5 font-semibold text-brand-700'
                    : 'rounded-md px-2 py-0.5 text-gray-500 hover:bg-gray-100'
                }
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        {/* Brand Header */}
        <div className="mb-5 text-center">
          <img
            src={logo}
            alt="SEDT logo"
            className="mx-auto mb-3 h-20 w-20 object-contain drop-shadow"
          />
          <h1 className="text-xl font-bold tracking-tight text-gray-900">
            {t('Kishori Vikas Programme')}
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            {t('Socio-Economic Development Trust (SEDT)')}
          </p>
        </div>

        {/* Mode Switch Tabs (Log in / Sign up) */}
        <div className="mb-5 flex rounded-xl bg-gray-100/90 p-1 text-xs sm:text-sm font-medium">
          <button
            type="button"
            onClick={() => {
              setOverrideMode('login')
              setError(null)
            }}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 transition-all ${
              mode === 'login'
                ? 'bg-white font-semibold text-brand-800 shadow-sm'
                : 'text-gray-500 hover:text-gray-900'
            }`}
          >
            <LogIn className="h-4 w-4" />
            {t('Log in')}
          </button>
          <button
            type="button"
            onClick={() => {
              setOverrideMode('signup')
              setError(null)
            }}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 transition-all ${
              mode === 'signup'
                ? 'bg-white font-semibold text-brand-800 shadow-sm'
                : 'text-gray-500 hover:text-gray-900'
            }`}
          >
            <UserPlus className="h-4 w-4" />
            {t('Sign up')}
          </button>
        </div>

        {mode === 'login' ? (
          <form onSubmit={submit}>
            <ErrorBox message={error} />
            <div className="space-y-3">
              <Field label={t('Mobile number or email')}>
                <Input
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  autoComplete="username"
                  required
                />
              </Field>
              <Field label={t('Password')}>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </Field>
              <Button
                type="submit"
                className="mt-1 w-full py-2.5 shadow-md shadow-brand-800/15"
                busy={busy}
              >
                {t('Log in')}
              </Button>
            </div>
            <div className="mt-4 text-center">
              <button
                type="button"
                onClick={() => {
                  setOverrideMode('signup')
                  setError(null)
                }}
                className="text-xs text-gray-500 hover:text-brand-700"
              >
                {t('Need an account?')}{' '}
                <span className="font-semibold text-brand-700 underline">
                  {t('Sign up / Request access')}
                </span>
              </button>
            </div>
          </form>
        ) : (
          <div>
            <div className="mb-4 rounded-xl border border-brand-100 bg-brand-50/70 p-3.5 text-xs text-brand-950 sm:text-sm">
              <div className="mb-1 flex items-center gap-1.5 font-semibold text-brand-900">
                <Sparkles className="h-4 w-4 text-brand-600" />
                {t('Volunteer & Stakeholder Registration')}
              </div>
              <p className="text-xs leading-relaxed text-gray-600">
                To safeguard field records and ensure assigned village access, volunteer and
                stakeholder accounts are provisioned by SEDT Programme Coordinators.
              </p>
            </div>

            <div className="space-y-2 text-xs sm:text-sm">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Contact Coordinators to register:
              </div>
              <a
                href="tel:+919922914102"
                className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-3 text-gray-700 shadow-sm transition hover:border-brand-500 hover:text-brand-700"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <Phone className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-[11px] text-gray-400">Call Programme Office</div>
                  <div className="font-medium text-gray-900">+91 99229 14102</div>
                </div>
              </a>
              <a
                href="mailto:sedtindia@gmail.com?subject=New%20Volunteer/Stakeholder%20Account%20Request%20-%20KVP"
                className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-3 text-gray-700 shadow-sm transition hover:border-brand-500 hover:text-brand-700"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <Mail className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-[11px] text-gray-400">Email Registration Desk</div>
                  <div className="truncate font-medium text-gray-900">sedtindia@gmail.com</div>
                </div>
              </a>
            </div>

            <div className="mt-5 text-center">
              <button
                type="button"
                onClick={() => {
                  setOverrideMode('login')
                  setError(null)
                }}
                className="text-xs font-semibold text-brand-700 hover:underline"
              >
                ← {t('Already have an account? Log in')}
              </button>
            </div>
          </div>
        )}

        {/* Organization attribution */}
        <p className="mt-6 border-t border-gray-100 pt-4 text-center text-xs text-gray-500">
          {t('A programme of')}{' '}
          <Link to="/home" className="font-medium text-brand-700 hover:underline">
            {t('Socio-Economic Development Trust')}
          </Link>
        </p>
      </div>
    </div>
  )
}
