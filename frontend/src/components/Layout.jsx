import {
  BarChart3,
  Bell,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
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
import logo from '../assets/SEDT_logo.png'
import { useAuth } from '../lib/auth'
import { humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { LANGUAGES, t, useLang } from '../lib/i18n'
import { Spinner, cx } from './ui'
import AdminAssistant from '../pages/AdminAssistant'
import MobileBottomNav from './MobileBottomNav'
import NoteCamModal from './NoteCamModal'

const NAV = [
  {
    section: 'Overview',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
    ],
  },
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
      { to: '/volunteers', label: 'Tais', icon: UserCog },
      { to: '/targets', label: 'Targets', icon: Target },
      { to: '/users', label: 'Users', icon: Users },
      { to: '/attendance', label: 'Tai attendance', icon: ClipboardCheck },
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

const VOLUNTEER_NAV = [
  {
    section: 'My work',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/field', label: 'Visits & daily reports', icon: ClipboardList },
      { to: '/targets', label: 'My targets', icon: Target },
    ],
  },
  {
    section: 'Village',
    items: [
      { to: '/girls', label: 'Girls', icon: Users },
      { to: '/groups', label: 'Groups', icon: Users },
      { to: '/cases', label: 'Follow-ups', icon: HeartPulse },
      { to: '/events', label: 'Events', icon: CalendarDays },
      { to: '/contacts', label: 'Village contacts', icon: Phone },
    ],
  },
  {
    section: 'My account',
    items: [
      { to: '/reports', label: 'My reports', icon: BarChart3 },
      { to: '/notifications', label: 'Notifications', icon: Bell },
    ],
  },
]

function Sidebar({ onNavigate, unread = 0, navItems, roleLabel }) {
  return (
    <nav className="flex h-full flex-col overflow-y-auto px-3 py-4 text-white">
      <div className="mb-6 flex items-center gap-3 px-2">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/30 bg-white p-1 shadow-sm">
          <img src={logo} alt="SEDT logo" className="h-full w-full object-contain" />
        </div>

        <div className="min-w-0 leading-tight">
          <div className="text-sm font-semibold text-white">
            {t('Kishori Vikas')}
          </div>
          <div className="mt-1 text-xs text-white/75">
            {t('Kishori Vikas Programme')}
          </div>
        </div>
      </div>

      {navItems.map((group) => (
        <div key={group.section} className="mb-5">
          <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-wider text-white/65">
            {t(group.section)}
          </div>

          <div className="space-y-1">
            {group.items.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cx(
                    'flex min-h-10 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-white font-semibold text-brand-900 shadow-sm'
                      : 'text-white hover:bg-white/15',
                  )
                }
              >
                <Icon className="h-[18px] w-[18px] shrink-0" />

                <span className="min-w-0 flex-1 leading-5">
                  {t(label)}
                </span>

                {to === '/notifications' && unread > 0 && (
                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-bold text-brand-900">
                    {unread}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      ))}

      <div className="mt-auto border-t border-white/20 px-3 pt-4 text-xs text-white/75">
        <FolderCog className="mr-2 inline h-4 w-4" />
        {t(roleLabel)}
      </div>
    </nav>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { lang, setLang } = useLang()
  const navItems = user?.role === 'volunteer' ? VOLUNTEER_NAV : NAV
  const roleLabel =
    user?.role === 'volunteer'
      ? 'Tai workspace'
      : (user?.role === 'stakeholder' || user?.role === 'super_admin')
      ? 'Stakeholder portal'
      : 'Admin portal'

  const [open, setOpen] = useState(false)
  const [noteCamOpen, setNoteCamOpen] = useState(false)
  const [noteCamAction, setNoteCamAction] = useState('CHECK-IN')
  const location = useLocation()
  const { data: unreadData, reload } = useFetch('/notifications/unread-count')
  const { data: todayAtt, reload: reloadTodayAtt } = useFetch(user?.role === 'volunteer' ? '/attendance/today' : null)

  useEffect(() => {
    const handleUpdate = () => {
      reloadTodayAtt?.()
    }
    window.addEventListener('kvp:attendance-updated', handleUpdate)
    return () => window.removeEventListener('kvp:attendance-updated', handleUpdate)
  }, [reloadTodayAtt])

  const isCheckedIn = Boolean(todayAtt?.checked_in)
  const isCheckedOut = Boolean(todayAtt?.checked_out)

  useEffect(() => {
    reload()
    setOpen(false)
  }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex h-full min-h-0">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 bg-brand-gradient lg:block">
        <Sidebar
          unread={unreadData?.unread}
          navItems={navItems}
          roleLabel={roleLabel}
        />
      </aside>

      {/* Mobile sidebar */}
      {open && (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          onClick={() => setOpen(false)}
        >
          <div className="absolute inset-0 bg-black/50" />

          <aside
            className="absolute inset-y-0 left-0 w-72 bg-brand-gradient shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="absolute right-3 top-3 z-10 rounded-lg p-2 text-white hover:bg-white/15"
              onClick={() => setOpen(false)}
              aria-label={t('Close menu')}
            >
              <X className="h-5 w-5" />
            </button>

            <Sidebar
              onNavigate={() => setOpen(false)}
              unread={unreadData?.unread}
              navItems={navItems}
              roleLabel={roleLabel}
            />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Brand header */}
        <header className="relative z-10 flex min-h-[66px] flex-wrap items-center justify-between gap-3 bg-brand-gradient px-4 py-3 text-white shadow-md sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              className="rounded-lg p-2 text-white hover:bg-white/15 lg:hidden"
              onClick={() => setOpen(true)}
              aria-label={t('Open menu')}
            >
              <Menu className="h-5 w-5" />
            </button>

            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white p-0.5 shadow-sm">
              <img src={logo} alt="SEDT logo" className="h-full w-full object-contain" />
            </div>

            <div className="hidden min-w-0 text-sm font-medium text-white sm:block">
              {t('KVP Digital Field Management & Impact Reporting')}
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3 sm:gap-4">
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              className="max-w-28 rounded-lg border border-white/50 bg-white px-2 py-2 text-xs font-medium text-black outline-none focus:ring-2 focus:ring-white/60"
              aria-label={t('Language')}
            >
              {LANGUAGES.map((language) => (
                <option key={language.value} value={language.value}>
                  {language.label}
                </option>
              ))}
            </select>

            <div className="max-w-32 text-right leading-tight">
              <div className="truncate text-sm font-semibold text-white">
                {user?.name}
              </div>
              <div className="mt-1 text-xs text-white/75">
                {user?.role === 'volunteer' ? t('Tai') : (user?.role === 'stakeholder' || user?.role === 'super_admin') ? t('Stakeholder') : t('Admin')}
              </div>
            </div>

            <button
              type="button"
              onClick={logout}
              className="rounded-lg p-2 text-white transition hover:bg-white/15"
              title={t('Log out')}
              aria-label={t('Log out')}
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </header>

        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          <Suspense fallback={<Spinner />}>
            <Outlet />
          </Suspense>
        </main>
      </div>

      {user?.role === 'volunteer' && (
        <MobileBottomNav
          onOpenMenu={() => setOpen(true)}
          onOpenCheckIn={() => {
            if (isCheckedOut) return
            setNoteCamAction(isCheckedIn ? 'CHECK-OUT' : 'CHECK-IN')
            setNoteCamOpen(true)
          }}
          checkedIn={isCheckedIn}
          checkedOut={isCheckedOut}
        />
      )}

      {user?.role === 'volunteer' && (
        <NoteCamModal
          open={noteCamOpen}
          onClose={() => setNoteCamOpen(false)}
          action={noteCamAction}
          user={user}
          villages={user?.villages || (user?.village ? [user.village] : [])}
          onSuccess={() => {
            setNoteCamOpen(false)
            reloadTodayAtt?.()
            window.dispatchEvent(new CustomEvent('kvp:attendance-updated'))
          }}
        />
      )}

      {(user?.role === 'admin' || user?.role === 'stakeholder' || user?.role === 'super_admin') && <AdminAssistant />}
    </div>
  )
}