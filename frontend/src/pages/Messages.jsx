import { Send } from 'lucide-react'
import { useState } from 'react'
import { Button, Card, ErrorBox, Field, Input, PageHeader, Pagination, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from '../components/ui'
import api from '../lib/api'
import { fmtDateTime, humanize } from '../lib/format'
import { useAction, useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

function Outbox() {
  const [f, setF] = useState({ status: '', purpose: '' })
  const [page, setPage] = useState(1)
  const [test, setTest] = useState({ to: '', body: 'KVP test message / चाचणी संदेश' })
  const [result, setResult] = useState(null)
  const { data, error, reload } = useFetch('/messages', { ...f, page, page_size: 30 })
  const { busy, error: actErr, run } = useAction()
  const sendTest = () => run(async () => { setResult((await api.post('/messages/test-sms', test)).data); reload() }).catch(() => {})
  return (
    <div className="space-y-4">
      <Card title={t('Send a test SMS')} actions={<span className="text-xs text-gray-500">{t('Configure the SMS provider under Configuration → Providers (type “sms”)')}</span>}>
        <ErrorBox message={actErr} />
        {result && <p className="mb-2 text-sm">{t('Result:')} <StatusBadge value={result.status} /> {result.error}</p>}
        <div className="grid gap-2 sm:grid-cols-4">
          <Input placeholder={t('Mobile number')} value={test.to} onChange={(e) => setTest({ ...test, to: e.target.value })} />
          <div className="sm:col-span-2"><Textarea rows={1} value={test.body} onChange={(e) => setTest({ ...test, body: e.target.value })} /></div>
          <Button icon={Send} busy={busy} disabled={!test.to} onClick={sendTest}>{t('Send test')}</Button>
        </div>
      </Card>
      <Card padded={false} title={t("SMS outbox (messages to girls' families)")} actions={<>
        <Select options={['sent', 'logged', 'failed', 'skipped', 'queued']} placeholder={t('Any status')} value={f.status} onChange={(e) => { setF({ ...f, status: e.target.value }); setPage(1) }} />
        <Select options={['event_participant_reminder', 'test']} placeholder={t('Any purpose')} value={f.purpose} onChange={(e) => { setF({ ...f, purpose: e.target.value }); setPage(1) }} />
      </>}>
        <ErrorBox message={error} />
        {data?.by_status && <div className="flex flex-wrap gap-3 px-4 pt-3 text-xs">{Object.entries(data.by_status).map(([k, n]) => <span key={k}><StatusBadge value={k} /> {n}</span>)}</div>}
        {!data ? <Spinner /> : (
          <>
            <Table columns={[
              { key: 'created_at', label: t('When'), render: (m) => fmtDateTime(m.created_at) },
              { key: 'to', label: t('To'), render: (m) => m.to || '—' },
              { key: 'recipient_name', label: t('For') },
              { key: 'purpose', label: t('Purpose'), render: (m) => humanize(m.purpose) },
              { key: 'body', label: t('Message'), render: (m) => <span className="line-clamp-2 max-w-md">{m.body}</span> },
              { key: 'status', label: t('Status'), render: (m) => <span><StatusBadge value={m.status} />{m.error && <span className="block text-xs text-gray-500">{m.error}</span>}</span> },
            ]} rows={data.items} empty={t('No messages yet. Turn on “SMS reminder” when scheduling an event.')} />
            <Pagination page={page} pageSize={30} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}

function SyncStatus() {
  const [hours, setHours] = useState(48)
  const { data } = useFetch('/sync/status', { stale_after_hours: hours })
  return (
    <Card title={t('Offline sync status (field devices)')} actions={<Field><Input type="number" min={1} value={hours} onChange={(e) => setHours(e.target.value)} /></Field>}>
      <p className="mb-3 text-xs text-gray-500">{t('Devices report here after each sync attempt from the volunteer app. Stale = no report within {n} hours.', { n: hours })}</p>
      {!data ? <Spinner /> : (
        <>
          <div className="mb-3 flex gap-4 text-sm">{t('Failed')} <b>{data.counts.failed}</b> {t('· Pending')} <b>{data.counts.pending}</b> {t('· Stale')} <b>{data.counts.stale}</b> {t('· Devices')} <b>{data.counts.total}</b></div>
          <Table columns={[
            { key: 'user_name', label: t('User'), className: 'font-medium' },
            { key: 'device_id', label: t('Device') },
            { key: 'state', label: t('State'), render: (s) => <StatusBadge value={s.state} /> },
            { key: 'pending', label: t('Pending'), className: 'tabular text-right' },
            { key: 'failed', label: t('Failed'), className: 'tabular text-right' },
            { key: 'last_report_at', label: t('Last report'), render: (s) => <span className={s.stale ? 'text-red-700' : ''}>{fmtDateTime(s.last_report_at)}</span> },
            { key: 'app_version', label: t('App') },
          ]} rows={data.devices} empty={t('No devices have reported yet. This fills in once volunteers use the field app.')} />
        </>
      )}
    </Card>
  )
}

export default function Messages() {
  const [tab, setTab] = useState('sms')
  return (
    <div>
      <PageHeader title={t('SMS & sync')} subtitle={t("Messages sent to beneficiaries' families and the offline-sync health of field devices")} />
      <Tabs tabs={[{ value: 'sms', label: t('SMS outbox') }, { value: 'sync', label: t('Sync status') }]} value={tab} onChange={setTab} />
      {tab === 'sms' ? <Outbox /> : <SyncStatus />}
    </div>
  )
}
