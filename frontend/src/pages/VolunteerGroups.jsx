import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, ErrorBox, PageHeader, Spinner, StatusBadge, Table } from '../components/ui'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

export default function VolunteerGroups() {
  const [type, setType] = useState('')
  const { data, error, loading } = useFetch('/groups', { page: 1, page_size: 200, group_type: type })
  return <div>
    <PageHeader title={t('My village groups')} subtitle={t('Groups available in your assigned village. Group setup is managed by a Stakeholder.')} />
    <Card padded={false}>
      <div className="flex flex-wrap gap-2 border-b border-gray-100 p-3">
        {[['', 'All groups'], ['kishori', 'Kishori groups'], ['bal_panchayat', 'Bal Panchayat']].map(([value, label]) => <button key={value} type="button" onClick={() => setType(value)} className={`rounded-full border px-3 py-1.5 text-sm ${type === value ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-300 text-gray-600'}`}>{t(label)}</button>)}
      </div>
      <ErrorBox message={error} />
      {loading && !data ? <Spinner /> : <Table columns={[
        { key: 'name', label: t('Group'), className: 'font-medium' },
        { key: 'group_type', label: t('Type'), render: (r) => t(r.group_type === 'bal_panchayat' ? 'Bal Panchayat' : 'Kishori group') },
        { key: 'group_number', label: t('Group number') },
        { key: 'meeting_schedule', label: t('Meeting schedule'), render: (r) => r.meeting_schedule ? `${r.meeting_schedule.frequency || ''}${r.meeting_schedule.time ? ` · ${r.meeting_schedule.time}` : ''}` : '—' },
        { key: 'is_active', label: t('Status'), render: (r) => <StatusBadge value={r.is_active ? 'active' : 'inactive'} /> },
        { key: 'open', label: '', render: (r) => <Link className="text-brand-700 hover:underline" to={`/groups/${r.id}`}>{t('View girls')}</Link> },
      ]} rows={data?.items} empty={t('No groups are assigned to this village yet.')} />}
    </Card>
  </div>
}
