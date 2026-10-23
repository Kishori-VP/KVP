import { BellRing, CheckCheck, Megaphone, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { VillageSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Select, Spinner, StatusBadge, Textarea, cx } from '../components/ui'
import api, { errorMessage } from '../lib/api'
import { fmtDateTime, humanize } from '../lib/format'
import { useAction, useFetch } from '../lib/hooks'
import { currentSubscription, disablePush, enablePush, pushSupported } from '../lib/push'
import { t } from '../lib/i18n'
import { useAuth } from '../lib/auth'

const LINK = { case: (id) => `/cases/${id}`, event: (id) => `/events/${id}`, target: () => '/targets', generated_report: () => '/reports', village: (id) => `/villages/${id}`, home_visit: () => '/field' }

function PushToggle() {
  const [on, setOn] = useState(null)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { currentSubscription().then((s) => setOn(Boolean(s))).catch(() => setOn(false)) }, [])
  if (!pushSupported()) return <span className="text-xs text-gray-500">{t('Push not supported in this browser')}</span>
  const toggle = async () => {
    setBusy(true)
    setMsg(null)
    try {
      if (on) { await disablePush(); setOn(false) } else { await enablePush(); setOn(true); await api.post('/push/test') }
    } catch (e) {
      setMsg(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Button size="sm" variant="secondary" icon={BellRing} busy={busy} onClick={toggle}>{on ? t('Disable push on this device') : t('Enable push on this device')}</Button>
      {msg && <span className="text-xs text-red-700">{msg}</span>}
    </span>
  )
}

function Announce({ open, onClose }) {
  const [f, setF] = useState({ audience: 'all_volunteers', severity: 'info', title: '', message: '' })
  const [sent, setSent] = useState(null)
  const { busy, error, run } = useAction()
  const send = () => run(async () => setSent((await api.post('/notifications/announce', { ...f, village_id: f.village_id || null })).data.sent)).catch(() => {})
  return (
    <Modal open={open} title={t('Send an announcement / job instruction')} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Close')}</Button><Button busy={busy} disabled={f.title.length < 3 || !f.message} onClick={send}>{t('Send')}</Button></>}>
      <ErrorBox message={error} />
      {sent !== null && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-900">{t('Sent to {n} user(s).', { n: sent })}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Audience')}><Select options={['all_volunteers', 'all_stakeholders', 'everyone', 'village']} value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })} /></Field>
        {f.audience === 'village' && <Field label={t('Village')}><VillageSelect value={f.village_id} onChange={(v) => setF({ ...f, village_id: v })} placeholder={t('Select')} /></Field>}
        <Field label={t('Priority')}><Select options={['info', 'low', 'medium', 'high', 'critical']} value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })} /></Field>
      </div>
      <Field label={t('Title *')}><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <Field label={t('Message *')}><Textarea value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></Field>
    </Modal>
  )
}

export default function Notifications() {
  const { user } = useAuth()
  const isStakeholder = user?.role === 'admin' || user?.role === 'stakeholder' || user?.role === 'super_admin'
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [page, setPage] = useState(1)
  const [announcing, setAnnouncing] = useState(false)
  const [checks, setChecks] = useState(null)
  const { data, error, loading, reload } = useFetch('/notifications', { unread_only: unreadOnly || '', page, page_size: 30 })
  const { busy, run } = useAction()
  const markAll = () => run(async () => { await api.post('/notifications/read-all'); reload() }).catch(() => {})
  const runChecks = () => run(async () => { setChecks((await api.post('/notifications/run-checks')).data); reload() }).catch(() => {})
  const open = async (n) => { if (!n.is_read) { await api.post(`/notifications/${n.id}/read`); reload() } }
  return (
    <div>
      <PageHeader title={t('Notifications & alerts')} subtitle={t('Reminders, missed targets, overdue reports and case escalations')}
        actions={<>
          <PushToggle />
          {isStakeholder && <Button variant="secondary" icon={RefreshCw} busy={busy} onClick={runChecks}>{t('Run checks now')}</Button>}
          {isStakeholder && <Button variant="secondary" icon={Megaphone} onClick={() => setAnnouncing(true)}>{t('Announce')}</Button>}
          <Button variant="secondary" icon={CheckCheck} onClick={markAll}>{t('Mark all read')}</Button>
        </>} />
      {checks && <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-900">{t('New')}: {Object.entries(checks).map(([k, n]) => `${humanize(k)} ${n}`).join(' · ')}</p>}
      <Card padded={false} title={t('{n} unread', { n: data?.unread ?? 0 })} actions={<Select options={[{ value: 'unread', label: t('Unread only') }]} placeholder={t('All notifications')} value={unreadOnly ? 'unread' : ''} onChange={(e) => { setUnreadOnly(e.target.value === 'unread'); setPage(1) }} />}>
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <ul className="divide-y divide-gray-100">
            {(data?.items || []).map((n) => {
              const to = n.entity_type && LINK[n.entity_type]?.(n.entity_id)
              const body = (
                <div className={cx('flex gap-3 px-4 py-3', !n.is_read && 'bg-brand-50/50')}>
                  <span className={cx('mt-1.5 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-transparent' : 'bg-brand-600')} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-gray-900">{n.title}</span>
                      {n.severity !== 'info' && <StatusBadge value={n.severity} />}
                      <Badge>{humanize(n.type)}</Badge>
                    </div>
                    {n.message && <p className="mt-0.5 text-sm text-gray-600">{n.message}</p>}
                    <p className="mt-0.5 text-xs text-gray-400">{fmtDateTime(n.created_at)}</p>
                  </div>
                </div>
              )
              return <li key={n.id} onClick={() => open(n)} className="cursor-pointer hover:bg-gray-50">{to ? <Link to={to}>{body}</Link> : body}</li>
            })}
            {!data?.items?.length && <li className="py-8 text-center text-sm text-gray-500">{t('No notifications.')}</li>}
          </ul>
        )}
        <Pagination page={page} pageSize={30} total={data?.total} onPage={setPage} />
      </Card>
      {isStakeholder && <Announce key={String(announcing)} open={announcing} onClose={() => setAnnouncing(false)} />}
    </div>
  )
}
