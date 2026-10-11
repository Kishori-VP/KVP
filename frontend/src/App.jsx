import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import { AuthProvider, useAuth } from './lib/auth'
import { LanguageProvider, t } from './lib/i18n'
import Login from './pages/Login'

// Pages load on demand to keep the first download small on mobile data.
const AuditLog = lazy(() => import('./pages/AuditLog'))
const CaseDetail = lazy(() => import('./pages/CaseDetail'))
const Cases = lazy(() => import('./pages/Cases'))
const Contacts = lazy(() => import('./pages/Contacts'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const EventDetail = lazy(() => import('./pages/EventDetail'))
const Events = lazy(() => import('./pages/Events'))
const FieldRecords = lazy(() => import('./pages/FieldRecords'))
const GirlDetail = lazy(() => import('./pages/GirlDetail'))
const Girls = lazy(() => import('./pages/Girls'))
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
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'stakeholder') {
    return (
      <div className="p-10 text-center text-sm text-gray-600">
        {t('This portal is for Stakeholders. Volunteers will use the KVP field app.')}
      </div>
    )
  }
  return children
}

export default function App() {
  return (
    <AuthProvider>
      <LanguageProvider>
      <BrowserRouter>
        <Suspense fallback={<Spinner />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <Protected>
                <Layout />
              </Protected>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="girls" element={<Girls />} />
            <Route path="girls/:id" element={<GirlDetail />} />
            <Route path="cases" element={<Cases />} />
            <Route path="cases/:id" element={<CaseDetail />} />
            <Route path="events" element={<Events />} />
            <Route path="events/:id" element={<EventDetail />} />
            <Route path="field" element={<FieldRecords />} />
            <Route path="volunteers" element={<Volunteers />} />
            <Route path="volunteers/:id" element={<VolunteerDetail />} />
            <Route path="targets" element={<Targets />} />
            <Route path="users" element={<Users />} />
            <Route path="master" element={<MasterData />} />
            <Route path="villages" element={<Villages />} />
            <Route path="villages/:id" element={<VillageDetail />} />
            <Route path="contacts" element={<Contacts />} />
            <Route path="reports" element={<Reports />} />
            <Route path="notifications" element={<Notifications />} />
            <Route path="messages" element={<Messages />} />
            <Route path="settings" element={<Settings />} />
            <Route path="audit" element={<AuditLog />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        </Suspense>
      </BrowserRouter>
      </LanguageProvider>
    </AuthProvider>
  )
}
