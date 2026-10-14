import {
  BarChart3,
  Bell,
  CalendarDays,
  ClipboardList,
  FileText,
  FolderCog,
  HeartPulse,
  History,
  LayoutDashboard,
  LogOut,
  MapPinned,
  Menu,
  MessageSquare,
  Phone,
  Settings,
  Target,
  UserCog,
  Users,
  X,
} from 'lucide-react'
import { Suspense, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { LANGUAGES, t, useLang } from '../lib/i18n'
import { Spinner, cx } from './ui'

const NAV = [
  { section: 'Overview', items: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true }] },
  {
    section: 'Programme',
    items: [
      { to: '/girls', label: 'Girls', icon: Users },
      { to: '/cases', label: 'Cases', icon: HeartPulse },
      { to: '/events', label: 'Events', icon: CalendarDays },
      { to: '/field', label: 'Field records', icon: ClipboardList },
    ],
  },
  {
    section: 'Team',
    items: [
      { to: '/volunteers', label: 'Volunteers', icon: UserCog },
      { to: '/targets', label: 'Targets', icon: Target },
      { to: '/users', label: 'Users', icon: Users },
    ],
  },
  {
    section: 'Villages',
    items: [
      { to: '/villages', label: 'Villages', icon: MapPinned },
      { to: '/master', label: 'Groups & talukas', icon: Users },
      { to: '/contacts', label: 'Contacts', icon: Phone },
    ],
  },
  {
    section: 'Insights',
    items: [
      { to: '/reports', label: 'Reports', icon: BarChart3 },
      { to: '/notifications', label: 'Notifications', icon: Bell },
      { to: '/messages', label: 'SMS & sync', icon: MessageSquare },
    ],
  },
  {
    section: 'Admin',
    items: [
      { to: '/settings', label: 'Configuration', icon: Settings },
      { to: '/audit', label: 'Audit log', icon: History },
    ],
  },
]

function Sidebar({ onNavigate, unread }) {
  return (
    <nav className="flex h-full flex-col overflow-y-auto px-3 py-4">
      <div className="bg-brand-gradient mb-6 flex items-center gap-3 rounded-xl p-3 text-white shadow-sm">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/15 text-sm font-bold ring-1 ring-white/25">KVP</div>
        <div className="min-w-0 leading-tight">
          <div className="truncate text-sm font-semibold">{t('Kishori Vikas')}</div>
          <div className="mt-0.5 truncate text-xs text-white/75">{t('Kishori Vikas Programme')}</div>
        </div>
      </div>
      {NAV.map((group) => (
        <div key={group.section} className="mb-3">
          <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-gray-400">{t(group.section)}</div>
          {group.items.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cx(
                  'mb-0.5 flex min-h-9 items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600',
                  isActive ? 'bg-brand-gradient font-medium text-white shadow-sm' : 'text-gray-600 hover:bg-brand-50 hover:text-brand-800',
                )
              }
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1">{t(label)}</span>
              {to === '/notifications' && unread > 0 && (
                <span className="rounded-full bg-brand-600 px-1.5 text-[11px] font-semibold text-white">{unread}</span>
              )}
            </NavLink>
          ))}
        </div>
      ))}
      <div className="mt-auto px-2 pt-4 text-[11px] text-gray-400">
        <FolderCog className="mr-1 inline h-3 w-3" /> {t('Stakeholder portal')}
      </div>
    </nav>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { lang, setLang } = useLang()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const { data: unreadData, reload } = useFetch('/notifications/unread-count')

  useEffect(() => {
    reload()
  }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-gray-200/80 bg-white lg:block">
        <Sidebar unread={unreadData?.unread} />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/30" />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-gray-200 bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="absolute right-2 top-2 rounded p-1 text-gray-500" onClick={() => setOpen(false)} aria-label={t('Close menu')}>
              <X className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} unread={unreadData?.unread} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-gray-200/80 bg-white/90 px-4 py-3 backdrop-blur-md">
          <button type="button" className="rounded p-1 text-gray-600 lg:hidden" onClick={() => setOpen(true)} aria-label={t('Open menu')}>
            <Menu className="h-5 w-5" />
          </button>
          <div className="hidden text-sm text-gray-500 lg:block">
            <FileText className="mr-1 inline h-4 w-4" /> {t('KVP Digital Field Management & Impact Reporting')}
          </div>
          <div className="flex items-center gap-3">
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700 shadow-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              aria-label={t('Language')}
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
            <div className="text-right leading-tight">
              <div className="text-sm font-medium text-gray-900">{user?.name}</div>
              <div className="text-xs capitalize text-gray-500">{humanize(user?.role)}</div>
            </div>
            <button type="button" onClick={logout} className="rounded-lg p-2 text-gray-500 transition-colors hover:bg-brand-50 hover:text-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600" title={t('Log out')} aria-label={t('Log out')}>
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          <Suspense fallback={<Spinner />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
