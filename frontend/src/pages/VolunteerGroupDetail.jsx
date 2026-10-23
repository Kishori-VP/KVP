import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Card, ErrorBox, PageHeader, Spinner, Table } from '../components/ui'
import { fmtDate, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

export default function VolunteerGroupDetail() {
  const { id } = useParams()
  const { data, error, loading } = useFetch(`/groups/${id}`)
  if (loading && !data) return <Spinner />
  return <div className="space-y-4">
    <Link to="/groups" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" />{t('My village groups')}</Link>
    <ErrorBox message={error} />
    {data && <>
      <PageHeader title={localName(data)} subtitle={`${humanize(data.group_type)}${data.group_number ? ` · ${data.group_number}` : ''}`} />
      <Card title={t('Group details')}>
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <div><span className="text-gray-500">{t('Meeting frequency')}</span><p className="font-medium">{humanize(data.meeting_schedule?.frequency || 'not set')}</p></div>
          <div><span className="text-gray-500">{t('Meeting time')}</span><p className="font-medium">{data.meeting_schedule?.time || '—'}</p></div>
          <div><span className="text-gray-500">{t('Girls registered')}</span><p className="font-medium">{data.girl_count || 0}</p></div>
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
    </>}
  </div>
}
