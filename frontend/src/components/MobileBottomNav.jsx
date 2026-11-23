import {
  CalendarDays,
  Camera,
  CheckCircle2,
  ClipboardList,
  Hourglass,
  Menu,
  Users,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { t } from '../lib/i18n'
import { cx } from './ui'

export default function MobileBottomNav({
  onOpenCheckIn,
  onOpenMenu,
  checkedIn = false,
  checkedOut = false,
  checkoutLocked = false,
  checkoutRemaining = '',
}) {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-30 flex h-[calc(4rem+env(safe-area-inset-bottom,0px))] items-center justify-around border-t border-gray-200/80 bg-white/90 px-2 pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-md shadow-lg lg:hidden">
      {/* 1. Events (attendance itself is the centre NoteCam button) */}
      <NavLink
        to="/events"
        className={({ isActive }) =>
          cx(
            'flex flex-col items-center justify-center gap-1 px-2 py-1 text-[11px] font-medium transition active:scale-95',
            isActive ? 'text-brand-800 font-bold' : 'text-gray-500 hover:text-gray-900'
          )
        }
      >
        <CalendarDays className="h-5 w-5" />
        <span>{t('Events')}</span>
      </NavLink>

      {/* 2. Field Visits */}
      <NavLink
        to="/field"
        className={({ isActive }) =>
          cx(
            'flex flex-col items-center justify-center gap-1 px-2 py-1 text-[11px] font-medium transition active:scale-95',
            isActive ? 'text-brand-800 font-bold' : 'text-gray-500 hover:text-gray-900'
          )
        }
      >
        <ClipboardList className="h-5 w-5" />
        <span>{t('Visits')}</span>
      </NavLink>

      {/* 3. Center Action: NoteCam Check-In / Out / Completed */}
      {checkedOut ? (
        <button
          type="button"
          disabled
          className="-mt-5 flex h-13 w-13 flex-col items-center justify-center rounded-full border-4 border-white bg-emerald-600 text-white shadow-md cursor-default opacity-90"
          title={t('Attendance already completed for today. Daily attendance is taken only once.')}
          aria-label={t('Attendance completed for today')}
        >
          <CheckCircle2 className="h-6 w-6" />
        </button>
      ) : checkedIn && checkoutLocked ? (
        <button
          type="button"
          disabled
          className="-mt-5 flex h-13 min-w-13 flex-col items-center justify-center rounded-full border-4 border-white bg-gray-500 px-1 text-white shadow-md cursor-not-allowed"
          title={t('Check-out locked')}
          aria-label={`${t('Time left until check-out')}: ${checkoutRemaining}`}
        >
          <Hourglass className="h-4 w-4" />
          <span className="tabular font-mono text-[9px] font-bold leading-tight">{checkoutRemaining}</span>
        </button>
      ) : checkedIn ? (
        <button
          type="button"
          onClick={onOpenCheckIn}
          className="-mt-5 flex h-13 w-13 flex-col items-center justify-center rounded-full border-4 border-white bg-amber-600 text-white shadow-xl transition active:scale-90"
          title={t('NoteCam Check-Out')}
          aria-label={t('NoteCam Check-Out')}
        >
          <Camera className="h-6 w-6" />
        </button>
      ) : (
        <button
          type="button"
          onClick={onOpenCheckIn}
          className="-mt-5 flex h-13 w-13 flex-col items-center justify-center rounded-full border-4 border-white bg-brand-gradient text-white shadow-xl transition active:scale-90"
          title={t('NoteCam Check-In')}
          aria-label={t('NoteCam Check-In')}
        >
          <Camera className="h-6 w-6" />
        </button>
      )}

      {/* 4. Girls */}
      <NavLink
        to="/girls"
        className={({ isActive }) =>
          cx(
            'flex flex-col items-center justify-center gap-1 px-2 py-1 text-[11px] font-medium transition active:scale-95',
            isActive ? 'text-brand-800 font-bold' : 'text-gray-500 hover:text-gray-900'
          )
        }
      >
        <Users className="h-5 w-5" />
        <span>{t('Girls')}</span>
      </NavLink>

      {/* 5. Menu Drawer */}
      <button
        type="button"
        onClick={onOpenMenu}
        className="flex flex-col items-center justify-center gap-1 px-2 py-1 text-[11px] font-medium text-gray-500 transition hover:text-gray-900 active:scale-95"
      >
        <Menu className="h-5 w-5" />
        <span>{t('More')}</span>
      </button>
    </nav>
  )
}
