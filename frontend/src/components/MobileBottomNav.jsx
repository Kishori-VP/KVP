import {
  CalendarDays,
  Camera,
  ClipboardList,
  Home,
  Menu,
  Users,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { t } from '../lib/i18n'
import { cx } from './ui'

export default function MobileBottomNav({ onOpenCheckIn, onOpenMenu }) {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-30 flex h-16 items-center justify-around border-t border-gray-200 bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur shadow-lg lg:hidden">
      {/* 1. Dashboard */}
      <NavLink
        to="/"
        end
        className={({ isActive }) =>
          cx(
            'flex flex-col items-center justify-center gap-1 px-2 py-1 text-[11px] font-medium transition active:scale-95',
            isActive ? 'text-brand-800 font-bold' : 'text-gray-500 hover:text-gray-900'
          )
        }
      >
        <Home className="h-5 w-5" />
        <span>{t('Home')}</span>
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

      {/* 3. Center Action: NoteCam Check-In / Out */}
      <button
        type="button"
        onClick={onOpenCheckIn}
        className="-mt-5 flex h-13 w-13 flex-col items-center justify-center rounded-full border-4 border-white bg-brand-gradient text-white shadow-xl transition active:scale-90"
        title={t('NoteCam Attendance')}
      >
        <Camera className="h-6 w-6" />
      </button>

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
