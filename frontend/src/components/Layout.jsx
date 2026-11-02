import {
  Baby,
  BarChart3,
  Bell,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FolderCog,
  GraduationCap,
  HeartPulse,
  History,
  LayoutDashboard,
  LogOut,
  MapPinned,
  Menu,
  MessageSquare,
  Phone,
  PhoneCall,
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
      { to: '/children', label: 'Children (Bal Panchayat)', icon: Baby },
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
      { to: '/attendance', label: 'Volunteer attendance', icon: ClipboardCheck },
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
      { to: '/field', label: 'Visits, calls & records', icon: ClipboardList },
      { to: '/targets', label: 'My targets', icon: Target },
    ],
  },
  {
    section: 'Village',
    items: [
      { to: '/girls', label: 'Girls', icon: Users },
      { to: '/children', label: 'Children (Bal Panchayat)', icon: Baby },
      { to: '/external-girls', label: 'External girls', icon: GraduationCap },
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
      ? 'Volunteer workspace'
      : (user?.role === 'super_admin' || user?.role === 'stakeholder')
      ? 'Super Admin portal'
      : user?.role === 'admin_1'
      ? 'Admin-1 portal'
      : user?.role === 'admin_2'
      ? 'Admin-2 portal'
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
          <div className="absolute inset-0 bg-black/50 backdrop-blur-xs transition-opacity" />

          <aside
            className="absolute inset-y-0 left-0 w-72 sm:w-80 max-w-[85vw] bg-brand-gradient shadow-2xl flex flex-col pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-xl text-white/90 hover:bg-white/15 active:bg-white/25 active:scale-95 transition"
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
        <header className="relative z-20 flex h-14 sm:h-16 flex-nowrap items-center justify-between gap-1.5 sm:gap-4 bg-brand-gradient px-2.5 sm:px-6 text-white shadow-md select-none shrink-0 pt-[env(safe-area-inset-top)]">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3 shrink-0">
            <button
              type="button"
              className="flex h-9 w-9 sm:h-10 sm:w-10 shrink-0 items-center justify-center rounded-xl text-white transition hover:bg-white/15 active:bg-white/25 active:scale-95 lg:hidden focus-visible:outline-2 focus-visible:outline-white"
              onClick={() => setOpen(true)}
              aria-label={t('Open menu')}
            >
              <Menu className="h-5 w-5" />
            </button>

            <div className="flex h-8 w-8 sm:h-10 sm:w-10 shrink-0 items-center justify-center rounded-xl bg-white p-0.5 shadow-sm ring-1 ring-black/5">
              <img src={logo} alt="SEDT logo" className="h-full w-full object-contain" />
            </div>

            <div className="hidden min-w-0 md:block text-sm font-semibold tracking-tight text-white/95 truncate max-w-xs lg:max-w-md">
              {t('KVP Digital Field Management & Impact Reporting')}
            </div>
            <div className="hidden sm:block md:hidden min-w-0 text-sm font-bold tracking-tight text-white/95">
              {t('Kishori Vikas')}
            </div>
          </div>

          <div className="ml-auto flex items-center gap-1.5 sm:gap-3 shrink-0 flex-nowrap">
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              className="h-8 sm:h-9 w-auto rounded-lg border border-white/30 bg-white/95 px-2 text-xs font-semibold text-gray-800 shadow-sm outline-none transition hover:bg-white focus:ring-2 focus:ring-white/80 shrink-0 cursor-pointer"
              aria-label={t('Language')}
            >
              {LANGUAGES.map((language) => (
                <option key={language.value} value={language.value}>
                  {language.label}
                </option>
              ))}
            </select>

            <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
              <div
                className="flex h-8 w-8 sm:h-9 sm:w-9 shrink-0 items-center justify-center rounded-full bg-white/20 font-bold text-xs text-white border border-white/30 shadow-sm backdrop-blur-sm select-none"
                title={user?.name}
              >
                {user?.name ? user.name.trim().charAt(0).toUpperCase() : 'U'}
              </div>

              <div className="text-right leading-tight max-w-[75px] xs:max-w-[105px] sm:max-w-[150px] md:max-w-[200px]">
                <div className="truncate text-xs sm:text-sm font-semibold text-white" title={user?.name}>
                  {user?.name}
                </div>
                <div className="hidden sm:block truncate text-[10px] text-white/75">
                  {user?.role === 'volunteer'
                    ? t('Volunteer')
                    : (user?.role === 'super_admin' || user?.role === 'stakeholder')
                    ? t('Super Admin')
                    : user?.role === 'admin_1'
                    ? t('Admin-1')
                    : user?.role === 'admin_2'
                    ? t('Admin-2')
                    : t('Admin')}
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={logout}
              className="flex h-8 w-8 sm:h-9 sm:w-9 shrink-0 items-center justify-center rounded-xl text-white transition hover:bg-white/15 active:bg-white/25 active:scale-95 focus-visible:outline-2 focus-visible:outline-white"
              title={t('Log out')}
              aria-label={t('Log out')}
            >
              <LogOut className="h-4 w-4 sm:h-[18px] sm:w-[18px]" />
            </button>
          </div>
        </header>

        <main className={cx('min-h-0 min-w-0 flex-1 overflow-y-auto px-3.5 py-4 sm:px-6 sm:py-6', user?.role === 'volunteer' ? 'pb-24 lg:pb-6' : 'pb-6')}>
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

      {(user?.role === 'admin_1' || user?.role === 'admin_2' || user?.role === 'super_admin' || user?.role === 'admin' || user?.role === 'stakeholder') && <AdminAssistant />}
    </div>
  )
}