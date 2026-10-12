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
      <div className="mb-5 flex items-center gap-2 px-2">
        <div className="bg-brand-gradient flex h-9 w-9 items-center justify-center rounded-lg text-sm font-bold text-white">KVP</div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-gray-900">{t('Kishori Vikas')}</div>
          <div className="text-xs text-gray-500">{t('Kishori Vikas Programme')}</div>
        </div>
      </div>
      {NAV.map((group) => (
        <div key={group.section} className="mb-3">
          <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400">{t(group.section)}</div>
          {group.items.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cx(
                  'flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm',
                  isActive ? 'bg-brand-50 font-medium text-brand-800' : 'text-gray-700 hover:bg-gray-100',
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
      <aside className="hidden w-60 shrink-0 border-r border-black/10 bg-white lg:block">
        <Sidebar unread={unreadData?.unread} />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/30" />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="absolute right-2 top-2 rounded p-1 text-gray-500" onClick={() => setOpen(false)} aria-label={t('Close menu')}>
              <X className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} unread={unreadData?.unread} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-black/10 bg-white px-4 py-2.5">
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
              className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700"
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
            <button type="button" onClick={logout} className="rounded-lg p-2 text-gray-500 hover:bg-gray-100" title={t('Log out')} aria-label={t('Log out')}>
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          <Suspense fallback={<Spinner />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
