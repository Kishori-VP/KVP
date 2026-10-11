import { Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TalukaSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, PageHeader, Select, Spinner, StatusBadge, Table, Tabs } from '../components/ui'
import { useFetch } from '../lib/hooks'
import { Locations, VillageModal } from './MasterData'
import { t } from '../lib/i18n'

function VillageList() {
  const nav = useNavigate()
  const [f, setF] = useState({ taluka_id: '', q: '', status: '' })
  const [modal, setModal] = useState(null)
  const { data, error, reload } = useFetch('/villages', f)
  return (
    <Card padded={false}>
      <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm" placeholder={t('Search village, hamlet, spelling…')}
            value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        </div>
        <TalukaSelect value={f.taluka_id} onChange={(v) => setF({ ...f, taluka_id: v })} />
        <Select options={['active', 'inactive']} placeholder={t('Active & inactive')} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} />
      </div>
      <ErrorBox message={error} />
      {!data ? <Spinner /> : (
        <>
          <div className="px-3 pt-2 text-xs text-gray-500">{t('{n} villages', { n: data.length })}</div>
          <Table onRowClick={(v) => nav(`/villages/${v.id}`)} columns={[
            { key: 'name', label: t('Village'), className: 'font-medium' },
            { key: 'name_mr', label: 'गाव' },
            { key: 'taluka_name', label: t('Taluka') },
            { key: 'girl_count', label: t('Girls'), className: 'tabular text-right' },
            { key: 'kishori_group_count', label: t('Kishori groups'), className: 'tabular text-right' },
            { key: 'volunteer_count', label: t('Volunteer'), render: (v) => (v.volunteer_count ? v.volunteer_count : <Badge tone="yellow">{t('None yet')}</Badge>) },
            { key: 'location', label: t('Map'), render: (v) => (v.location ? <Badge tone="green">{t('Located')}</Badge> : <Badge>{t('No GPS')}</Badge>) },
            { key: 'status', label: t('Status'), render: (v) => <StatusBadge value={v.status} /> },
            { key: 'edit', label: '', render: (v) => <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setModal(v) }}>{t('Edit')}</Button> },
          ]} rows={data} empty={t('No villages match.')} />
        </>
      )}
      {modal && <VillageModal village={modal} onClose={() => setModal(null)} onSaved={() => { setModal(null); reload() }} />}
    </Card>
  )
}

export default function Villages() {
  const [tab, setTab] = useState('list')
  const [adding, setAdding] = useState(false)
  return (
    <div>
      <PageHeader title={t('Villages')} subtitle={t('Programme villages, their taluka, location and coverage. Volunteers are assigned from the Volunteers page.')}
        actions={<Button icon={Plus} onClick={() => setAdding(true)}>{t('Add village')}</Button>} />
      <Tabs tabs={[{ value: 'list', label: t('All villages') }, { value: 'locations', label: t('Set locations') }]} value={tab} onChange={setTab} />
      {tab === 'list' ? <VillageList key={String(adding)} /> : <Locations />}
      {adding && <VillageModal village={null} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); setTab('list') }} />}
    </div>
  )
}
