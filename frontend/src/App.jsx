import { Suspense, lazy, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import api from './lib/api'
import { AuthProvider, useAuth } from './lib/auth'
import { LanguageProvider, t } from './lib/i18n'
import Home from './pages/Home'
import Login from './pages/Login'

function WakingBanner() {
  const [waking, setWaking] = useState(false)

  useEffect(() => {
    // Eagerly ping backend on initial page load to start Render spin-up immediately
    api.get('/health').catch(() => {})

    function handleWaking(event) {
      setWaking(Boolean(event.detail?.waking))
    }

    window.addEventListener('kvp:backend-waking', handleWaking)
    return () => window.removeEventListener('kvp:backend-waking', handleWaking)
  }, [])

  if (!waking) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed top-3 left-1/2 -translate-x-1/2 z-[100] max-w-[92vw] sm:max-w-md px-4 py-2.5 rounded-xl bg-amber-600 text-white text-xs sm:text-sm font-medium shadow-2xl flex items-center gap-2.5"
    >
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
      </span>
      <span>{t('Connecting to Render… Free-tier server is waking up (~30-50s on initial load).')}</span>
    </div>
  )
}

// Pages load on demand to keep the first download small on mobile data.
const AuditLog = lazy(() => import('./pages/AuditLog'))
const VolunteerAttendance = lazy(() => import('./pages/VolunteerAttendance'))
const CaseDetail = lazy(() => import('./pages/CaseDetail'))
const Cases = lazy(() => import('./pages/Cases'))
const Contacts = lazy(() => import('./pages/Contacts'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const VolunteerDashboard = lazy(() => import('./pages/VolunteerDashboard'))
const VolunteerFieldRecords = lazy(() => import('./pages/VolunteerFieldRecords'))
const VolunteerContacts = lazy(() => import('./pages/VolunteerContacts'))
const VolunteerReports = lazy(() => import('./pages/VolunteerReports'))
const VolunteerGroups = lazy(() => import('./pages/VolunteerGroups'))
const VolunteerGroupDetail = lazy(() => import('./pages/VolunteerGroupDetail'))
const EventDetail = lazy(() => import('./pages/EventDetail'))
const Events = lazy(() => import('./pages/Events'))
const ExternalGirls = lazy(() => import('./pages/ExternalGirls'))
const FieldRecords = lazy(() => import('./pages/FieldRecords'))
const GirlDetail = lazy(() => import('./pages/GirlDetail'))
const Girls = lazy(() => import('./pages/Girls'))
const Children = lazy(() => import('./pages/Children'))
const MasterData = lazy(() => import('./pages/MasterData'))
const Messages = lazy(() => import('./pages/Messages'))
const Notifications = lazy(() => import('./pages/Notifications'))
const Reports = lazy(() => import('./pages/Reports'))
const Settings = lazy(() => import('./pages/settings/Settings'))
const Targets = lazy(() => import('./pages/Targets'))
const Users = lazy(() => import('./pages/Users'))
const VillageDetail = lazy(() => import('./pages/VillageDetail'))
const Villages = lazy(() => import('./pages/Villages'))
const VolunteerDetail = lazy(() => import('./pages/VolunteerDetail'))
const Volunteers = lazy(() => import('./pages/Volunteers'))

function Protected({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/home" replace />
  return children
}

function RoleHome() {
  const { user } = useAuth()
  return user?.role === 'volunteer' ? <VolunteerDashboard /> : <Dashboard />
}

function RoleSwitch({ stakeholder, volunteer }) {
  const { user } = useAuth()
  return user?.role === 'volunteer' ? volunteer : stakeholder
}

function StakeholderOnly({ children }) {
  const { user } = useAuth()
  return (user?.role === 'admin' || user?.role === 'stakeholder' || user?.role === 'super_admin') ? children : <Navigate to="/" replace />
}

function VolunteerOnly({ children }) {
  const { user } = useAuth()
  return user?.role === 'volunteer' ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <LanguageProvider>
      <BrowserRouter>
        <WakingBanner />
        <Suspense fallback={<Spinner />}>
        <Routes>
          <Route path="/home" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Login />} />
          <Route path="/register" element={<Login />} />
          <Route
            element={
              <Protected>
                <Layout />
              </Protected>
            }
          >
            <Route index element={<RoleHome />} />
            <Route path="girls" element={<Girls />} />
            <Route path="children" element={<Children />} />
            <Route path="girls/:id" element={<GirlDetail />} />
            <Route path="external-girls" element={<ExternalGirls />} />
            <Route path="cases" element={<Cases />} />
            <Route path="cases/:id" element={<CaseDetail />} />
            <Route path="events" element={<Events />} />
            <Route path="events/:id" element={<EventDetail />} />
            <Route path="field" element={<VolunteerOnly><VolunteerFieldRecords /></VolunteerOnly>} />
            <Route path="volunteers" element={<StakeholderOnly><Volunteers /></StakeholderOnly>} />
            <Route path="volunteers/:id" element={<StakeholderOnly><VolunteerDetail /></StakeholderOnly>} />
            <Route path="targets" element={<Targets />} />
            <Route path="users" element={<StakeholderOnly><Users /></StakeholderOnly>} />
            <Route path="master" element={<StakeholderOnly><MasterData /></StakeholderOnly>} />
            <Route path="villages" element={<StakeholderOnly><Villages /></StakeholderOnly>} />
            <Route path="villages/:id" element={<StakeholderOnly><VillageDetail /></StakeholderOnly>} />
            <Route path="groups" element={<VolunteerOnly><VolunteerGroups /></VolunteerOnly>} />
            <Route path="groups/:id" element={<VolunteerGroupDetail />} />
            <Route path="contacts" element={<RoleSwitch stakeholder={<Contacts />} volunteer={<VolunteerContacts />} />} />
            <Route path="reports" element={<RoleSwitch stakeholder={<Reports />} volunteer={<VolunteerReports />} />} />
            <Route path="notifications" element={<Notifications />} />
            <Route path="messages" element={<StakeholderOnly><Messages /></StakeholderOnly>} />
            <Route path="settings" element={<StakeholderOnly><Settings /></StakeholderOnly>} />
            <Route path="audit" element={<StakeholderOnly><AuditLog /></StakeholderOnly>} />
            <Route path="attendance" element={<StakeholderOnly><VolunteerAttendance /></StakeholderOnly>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        </Suspense>
      </BrowserRouter>
      </LanguageProvider>
    </AuthProvider>
  )
}
