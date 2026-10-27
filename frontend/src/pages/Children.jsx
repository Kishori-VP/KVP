import { Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import ChildModal from '../components/ChildModal'
import { GroupSelect, VillageSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Select, Spinner, Table } from '../components/ui'
import api from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAction, useFetch } from '../lib/hooks'
import { locale, localName, t } from '../lib/i18n'

const EMPTY = { q: '', village_id: '', group_id: '', registered: '' }

/** Every child in a Bal Panchayat, boys included. Children who are registered girls link to their profile. */
export default function Children() {
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const canManage = isSuperAdmin || user?.role === 'admin_1'
  const [filters, setFilters] = useState(EMPTY)
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const set = (k, v) => { setFilters((p) => ({ ...p, [k]: v, ...(k === 'village_id' ? { group_id: '' } : {}) })); setPage(1) }
  const { data, error, loading, reload } = useFetch('/children', { ...filters, page, page_size: 50 })

  const deleteChild = async (r) => {
    if (!window.confirm(t('Are you sure you want to delete {name} from Bal Panchayat?', { name: localName(r) }))) return
    const gId = r.group?.id || r.group_id
    const mId = r.member_id || r.id
    try {
      await api.delete(`/children/${gId}/${mId}`)
      reload()
    } catch (e) {
      alert(e.response?.data?.detail || e.message)
    }
  }

  return (
    <div>
      <PageHeader
        title={t('Children (Bal Panchayat)')}
        subtitle={t('All children in the Bal Panchayats, including boys')}
        actions={canManage && (
          <Button icon={Plus} onClick={() => setModal({ village_id: filters.village_id, group_id: filters.group_id })}>
            {t('Add Child')}
          </Button>
        )}
      />
      <Card padded={false}>
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm" placeholder={t('Search name…')} value={filters.q} onChange={(e) => set('q', e.target.value)} />
          </div>
          {user?.role !== 'volunteer' && <VillageSelect value={filters.village_id} onChange={(v) => set('village_id', v)} />}
          <GroupSelect villageId={filters.village_id} groupType="bal_panchayat" placeholder={t('All Bal Panchayats')} value={filters.group_id} onChange={(v) => set('group_id', v)} />
          <Select options={[{ value: 'true', label: t('Registered girls') }, { value: 'false', label: t('Not registered') }]} placeholder={t('Everyone')} value={filters.registered} onChange={(e) => set('registered', e.target.value)} />
        </div>
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <>
            <div className="px-3 pt-2 text-xs text-gray-500">{t('{n} children', { n: data?.total?.toLocaleString(locale()) })}</div>
            <Table
              columns={[
                { key: 'name', label: t('Name'), render: (r) => (r.girl_id
                  ? <Link className="text-brand-700 hover:underline" to={`/girls/${r.girl_id}`}>{localName(r)}</Link> : localName(r)) },
                { key: 'standard', label: t('Class'), render: (r) => r.standard || '—' },
                { key: 'phone', label: t('Mobile'), className: 'whitespace-nowrap', render: (r) => r.phone || '—' },
                { key: 'village', label: t('Village'), render: (r) => localName(r.village) || '—' },
                { key: 'group', label: t('Bal Panchayat'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/groups/${r.group.id}`}>{localName(r.group)}</Link> },
                { key: 'registered', label: '', render: (r) => (r.girl_id ? <Badge tone="brand">{t('Registered girl')}</Badge> : null) },
                ...(canManage ? [{
                  key: 'actions', label: '', render: (r) => (
                    <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setModal(r)}>{t('Edit')}</Button>
                      {isSuperAdmin && (
                        <Button size="sm" variant="ghost" className="text-red-600 hover:text-red-800" icon={Trash2} onClick={() => deleteChild(r)} />
                      )}
                    </div>
                  )
                }] : [])
              ]}
              rows={data?.items || []}
              empty={t('No children found.')}
            />
            <Pagination page={page} pageSize={50} total={data?.total} onPage={setPage} />
          </>
        )}
      </Card>

      {modal && (
        <ChildModal
          child={modal.name ? modal : null}
          defaultVillageId={modal.village_id || filters.village_id}
          defaultGroupId={modal.group_id || filters.group_id}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); reload() }}
        />
      )}
    </div>
  )
}
