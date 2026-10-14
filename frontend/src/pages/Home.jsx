import { Baby, BookOpen, HeartHandshake, LogIn, Mail, MapPin, Phone, Sprout, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import logo from '../assets/SEDT_logo.png'
import { useAuth } from '../lib/auth'
import { LANGUAGES, t, useLang } from '../lib/i18n'

// Public landing page introducing SEDT. Figures are taken from sedtindia.org.
const STATS = [
  { value: '1980', label: 'Working since' },
  { value: '2,254', label: 'Adolescent girls reached' },
  { value: '24', label: 'Villages under Kishori Vikas' },
  { value: '4,788', label: 'Children supported by Childline' },
]

const AREAS = [
  { icon: Baby, title: 'Child care', text: 'Swapnabhoomi home for homeless and orphaned children, and Childline Parbhani.' },
  { icon: BookOpen, title: 'Education & science', text: 'Discovery Science Center and Shree Sant Dnyaneshwar Vidyalaya.' },
  { icon: HeartHandshake, title: 'Women & girls', text: 'Kishori Vikas, Family Counseling Center and One Stop Center, Parbhani.' },
  { icon: Sprout, title: 'Livelihoods & health', text: 'Affordable farming, Bal Panchayats and HIV/AIDS targeted interventions.' },
]

export default function Home() {
  const { user } = useAuth()
  const { lang, setLang } = useLang()

  return (
    <div className="min-h-full bg-gradient-to-br from-brand-50 via-white to-brand-100/60">
      <header className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-8">
        <div className="flex items-center gap-3">
          <img src={logo} alt="SEDT logo" className="h-12 w-12 object-contain" />
          <div className="leading-tight">
            <div className="font-semibold text-gray-900">SEDT</div>
            <div className="text-xs text-gray-500">{t('Socio-Economic Development Trust')}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden gap-1 text-xs sm:flex">
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
          <Link
            to={user ? '/' : '/login'}
            className="bg-brand-gradient bg-brand-gradient-hover inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium text-white shadow-md shadow-brand-800/15"
          >
            <LogIn className="h-4 w-4" />
            {user ? t('Go to dashboard') : t('Log in')}
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-16 sm:px-8">
        <section className="grid items-center gap-10 py-10 md:grid-cols-[1.3fr_1fr] md:py-16">
          <div>
            <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-brand-600">{t('Kishori Vikas Programme')}</p>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              {t('Building knowledge, skills and confidence in adolescent girls')}
            </h1>
            <p className="mt-4 text-gray-600">
              {t('Socio-Economic Development Trust (SEDT) is a registered NGO established in 1980 by Mr. Suryakant Kulkarni. It works with poor and marginalised communities in the rural areas of Parbhani district, Marathwada, Maharashtra.')}
            </p>
            <p className="mt-3 text-gray-600">
              {t('Kishori Vikas is a step towards empowered and healthy communities. This portal helps SEDT stakeholders track girls, villages, volunteers, events and outcomes across the programme.')}
            </p>
          </div>
          <div className="flex justify-center">
            <img src={logo} alt="" className="w-56 drop-shadow-xl sm:w-72" />
          </div>
        </section>

        <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="rounded-2xl border border-white/80 bg-white/90 p-5 text-center shadow-sm">
              <div className="text-brand-gradient text-2xl font-bold sm:text-3xl">{s.value}</div>
              <div className="mt-1 text-xs text-gray-500 sm:text-sm">{t(s.label)}</div>
            </div>
          ))}
        </section>

        <section className="mt-14">
          <h2 className="mb-5 flex items-center gap-2 text-xl font-semibold text-gray-900">
            <Users className="h-5 w-5 text-brand-600" />
            {t('What SEDT does')}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {AREAS.map(({ icon: Icon, title, text }) => (
              <div key={title} className="rounded-2xl border border-white/80 bg-white/90 p-5 shadow-sm">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="font-semibold text-gray-900">{t(title)}</h3>
                <p className="mt-1 text-sm text-gray-600">{t(text)}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-14 rounded-2xl border border-white/80 bg-white/90 p-6 shadow-sm">
          <h2 className="mb-4 text-xl font-semibold text-gray-900">{t('Contact')}</h2>
          <div className="grid gap-4 text-sm text-gray-600 sm:grid-cols-3">
            <div className="flex gap-2">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
              <span>Post Kerwadi, Taluka Palam, District Parbhani, Maharashtra 431 720</span>
            </div>
            <a href="tel:+919922914102" className="flex gap-2 hover:text-brand-700">
              <Phone className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
              +91 99229 14102
            </a>
            <a href="mailto:sedtindia@gmail.com" className="flex gap-2 hover:text-brand-700">
              <Mail className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
              sedtindia@gmail.com
            </a>
          </div>
          <a href="https://sedtindia.org/" target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-medium text-brand-700 hover:underline">
            {t('Visit sedtindia.org')} →
          </a>
        </section>
      </main>
    </div>
  )
}
