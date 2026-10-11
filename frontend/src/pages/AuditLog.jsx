import { useState } from 'react'
import { Card, ErrorBox, Input, Modal, PageHeader, Pagination, Select, Spinner, Table } from '../components/ui'
import { fmtDateTime, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

const ACTIONS = ['create', 'update', 'delete', 'approve', 'reject', 'reassign', 'revise', 'verify', 'login', 'import', 'config_change', 'status_change', 'export']
const ENTITIES = ['user', 'girl', 'case', 'event', 'event_report', 'home_visit', 'activity_report', 'target', 'village', 'group', 'taluka', 'contact', 'setting', 'lookup', 'provider_config', 'report', 'report_template', 'report_schedule', 'media', 'message', 'master_data']

export default function AuditLog() {
  const [f, setF] = useState({ action: '', entity_type: '', start_date: '', end_date: '' })
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState(null)
  const { data, error, loading } = useFetch('/audit-logs', { ...f, page, page_size: 50 })
  const set = (k, v) => { setF({ ...f, [k]: v }); setPage(1) }
  return (
    <div>
      <PageHeader title={t('Audit log')} subtitle={t('Creation, edits, approvals, deletions, reassignments and configuration changes')} />
      <Card padded={false}>
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-4">
          <Select options={ACTIONS} placeholder={t('Any action')} value={f.action} onChange={(e) => set('action', e.target.value)} />
          <Select options={ENTITIES} placeholder={t('Any record type')} value={f.entity_type} onChange={(e) => set('entity_type', e.target.value)} />
          <Input type="date" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} />
          <Input type="date" value={f.end_date} onChange={(e) => set('end_date', e.target.value)} />
        </div>
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <>
            <Table onRowClick={setDetail} columns={[
              { key: 'at', label: t('When'), render: (r) => fmtDateTime(r.at), className: 'whitespace-nowrap' },
              { key: 'actor_name', label: t('Who') },
              { key: 'action', label: t('Action'), render: (r) => humanize(r.action) },
              { key: 'entity_type', label: t('Record'), render: (r) => humanize(r.entity_type) },
              { key: 'summary', label: t('Summary') },
              { key: 'changes', label: t('Fields changed'), render: (r) => (r.changes ? Object.keys(r.changes).join(', ') : '—') },
            ]} rows={data?.items} />
            <Pagination page={page} pageSize={50} total={data?.total} onPage={setPage} />
          </>
        )}
      </Card>
      {detail && (
        <Modal open wide title={detail.summary || humanize(detail.action)} onClose={() => setDetail(null)}>
          <p className="text-sm text-gray-600">{fmtDateTime(detail.at)} · {detail.actor_name} ({detail.actor_role})</p>
          {detail.changes && (
            <Table rowKey={(r) => r.field} columns={[
              { key: 'field', label: t('Field') },
              { key: 'from', label: t('Before'), render: (r) => <code className="text-xs">{JSON.stringify(r.from)}</code> },
              { key: 'to', label: t('After'), render: (r) => <code className="text-xs">{JSON.stringify(r.to)}</code> },
            ]} rows={Object.entries(detail.changes).map(([field, c]) => ({ field, ...c }))} />
          )}
          {detail.meta && <pre className="overflow-x-auto rounded-lg bg-gray-50 p-2 text-xs">{JSON.stringify(detail.meta, null, 2)}</pre>}
        </Modal>
      )}
    </div>
  )
}
