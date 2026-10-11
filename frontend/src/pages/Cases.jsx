import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LookupSelect, VillageSelect, VolunteerSelect } from '../components/pickers'
import { Card, Checkbox, ErrorBox, PageHeader, Pagination, Select, Spinner, StatusBadge, Table } from '../components/ui'
import { fmtDate, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

export default function Cases() {
  const nav = useNavigate()
  const [f, setF] = useState({ status: '', severity: '', category: '', village_id: '', assigned_to: '', overdue: false, stale: false, open_only: true })
  const [page, setPage] = useState(1)
  const set = (k, v) => { setF((p) => ({ ...p, [k]: v })); setPage(1) }
  const { data, error, loading } = useFetch('/cases', { ...f, overdue: f.overdue || '', stale: f.stale || '', open_only: f.open_only || '', page, page_size: 25 })
  return (
    <div>
      <PageHeader title={t('Cases & concerns')} subtitle={t("Child marriage risk, dropout, health and other concerns linked to Girl IDs. Open a new case from a girl's profile.")} />
      <Card padded={false}>
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-2 lg:grid-cols-5">
          <Select options={['open', 'in_progress', 'escalated', 'resolved', 'closed']} placeholder={t('Any status')} value={f.status} onChange={(e) => set('status', e.target.value)} />
          <Select options={['critical', 'high', 'medium', 'low']} placeholder={t('Any severity')} value={f.severity} onChange={(e) => set('severity', e.target.value)} />
          <LookupSelect type="case_category" value={f.category} onChange={(v) => set('category', v)} placeholder={t('Any category')} />
          <VillageSelect value={f.village_id} onChange={(v) => set('village_id', v)} />
          <VolunteerSelect value={f.assigned_to} onChange={(v) => set('assigned_to', v)} placeholder={t('Any assignee')} />
          <div className="flex flex-wrap gap-4 sm:col-span-2 lg:col-span-5">
            <Checkbox label={t('Open only')} checked={f.open_only} onChange={(e) => set('open_only', e.target.checked)} />
            <Checkbox label={t('Overdue')} checked={f.overdue} onChange={(e) => set('overdue', e.target.checked)} />
            <Checkbox label={t('No recent update')} checked={f.stale} onChange={(e) => set('stale', e.target.checked)} />
          </div>
        </div>
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <>
            <Table
              onRowClick={(r) => nav(`/cases/${r.id}`)}
              columns={[
                { key: 'case_code', label: t('Case'), className: 'font-medium whitespace-nowrap' },
                { key: 'girl_code', label: t('Girl ID') },
                { key: 'title', label: t('Title') },
                { key: 'category', label: t('Category'), render: (r) => humanize(r.category) },
                { key: 'severity', label: t('Severity'), render: (r) => <StatusBadge value={r.severity} /> },
                { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
                { key: 'due_date', label: t('Due'), render: (r) => <span className={r.is_overdue ? 'font-medium text-red-700' : ''}>{fmtDate(r.due_date)}</span> },
                { key: 'age_days', label: t('Age (days)'), className: 'tabular text-right' },
              ]}
              rows={data?.items}
              empty={t('No cases match these filters.')}
            />
            <Pagination page={page} pageSize={25} total={data?.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}
