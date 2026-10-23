import { ArrowLeft } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Card, ErrorBox, PageHeader, Spinner, Table } from '../components/ui'
import { fmtDate, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

export default function VolunteerGroupDetail() {
  const { id } = useParams()
  const { data, error, loading } = useFetch(`/groups/${id}`)
  const { user } = useAuth()
  const nav = useNavigate()
  const girlIds = new Set((data?.girls || []).map((g) => g.id))
  if (loading && !data) return <Spinner />
  return <div className="space-y-4">
    {user?.role === 'volunteer'
      ? <Link to="/groups" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" />{t('My village groups')}</Link>
      : <button type="button" onClick={() => nav(-1)} className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" />{t('Back')}</button>}
    <ErrorBox message={error} />
    {data && <>
      <PageHeader title={localName(data)} subtitle={`${humanize(data.group_type)}${data.group_number ? ` · ${data.group_number}` : ''}`} />
      <Card title={t('Group details')}>
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <div><span className="text-gray-500">{t('Meeting frequency')}</span><p className="font-medium">{humanize(data.meeting_schedule?.frequency || 'not set')}</p></div>
          <div><span className="text-gray-500">{t('Meeting time')}</span><p className="font-medium">{data.meeting_schedule?.time || '—'}</p></div>
          <div><span className="text-gray-500">{t('Girls registered')}</span><p className="font-medium">{data.girl_count || 0}</p></div>
          {data.member_count > 0 && <div><span className="text-gray-500">{t('Members')}</span><p className="font-medium">{data.member_count}</p></div>}
          <div><span className="text-gray-500">{t('Notes')}</span><p className="font-medium">{data.meeting_schedule?.notes || '—'}</p></div>
        </div>
      </Card>
      <Card title={t('Girls in this group')}>
        <Table columns={[
          { key: 'girl_code', label: t('Girl ID'), className: 'font-medium' },
          { key: 'name', label: t('Name'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/girls/${r.id}`}>{localName(r) || t('Not recorded')}</Link> },
          { key: 'dob', label: t('Date of birth'), render: (r) => fmtDate(r.dob) },
        ]} rows={data.girls} empty={t('No girls are currently linked to this group.')} />
      </Card>
      {data.members?.length > 0 && <Card title={t('Bal Panchayat members')}>
        <p className="mb-3 text-xs text-gray-500">{t('Every child in the Bal Panchayat, including boys. Registered girls link to their profile.')}</p>
        <Table columns={[
          { key: 'name', label: t('Name'), render: (m) => (m.girl_id && girlIds.has(m.girl_id)
            ? <Link className="text-brand-700 hover:underline" to={`/girls/${m.girl_id}`}>{m.name}</Link> : m.name) },
          { key: 'standard', label: t('Class'), render: (m) => m.standard || '—' },
          { key: 'phone', label: t('Mobile'), render: (m) => m.phone || '—' },
        ]} rows={data.members.map((m, i) => ({ ...m, id: m.girl_id || `m${i}` }))} />
      </Card>}
    </>}
  </div>
}
