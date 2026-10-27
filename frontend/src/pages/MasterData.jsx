import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { TalukaSelect, VillageSelect, VolunteerSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Select, Spinner, StatusBadge, Table, Tabs } from '../components/ui'
import api from '../lib/api'
import { useAuth } from '../lib/auth'
import { invalidateRefData, useAction, useFetch, useVillages } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

const hasCoord = (v) => v !== '' && v !== null && v !== undefined && !Number.isNaN(Number(v))

export function VillageModal({ village, onClose, onSaved }) {
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const [f, setF] = useState(village ? { ...village, hamlets: (village.hamlets || []).join(', '), aliases: (village.aliases || []).join(', '), lat: village.location?.lat ?? '', lng: village.location?.lng ?? '' } : { status: 'active', lat: '', lng: '' })
  const { busy, error, run } = useAction()
  const save = () => run(async () => {
    const split = (s) => (s || '').split(',').map((x) => x.trim()).filter(Boolean)
    const body = {
      name: f.name, name_mr: f.name_mr || null, taluka_id: f.taluka_id, pin_code: f.pin_code || null, status: f.status,
      hamlets: split(f.hamlets), aliases: split(f.aliases),
      location: hasCoord(f.lat) && hasCoord(f.lng) ? { lat: Number(f.lat), lng: Number(f.lng) } : null,
    }
    if (village) await api.patch(`/villages/${village.id}`, body)
    else await api.post('/villages', body)
    invalidateRefData()
    onSaved()
  }).catch(() => {})

  const remove = () => run(async () => {
    if (!window.confirm(t('Are you sure you want to delete {name}?', { name: village.name }))) return
    await api.delete(`/villages/${village.id}`)
    invalidateRefData()
    onSaved()
  }).catch(() => {})

  return (
    <Modal open title={village ? t('Edit {code}', { code: village.name }) : t('Add village')} onClose={onClose}
      footer={
        <div className="flex w-full items-center justify-between">
          <div>
            {village && isSuperAdmin && (
              <Button variant="danger" icon={Trash2} busy={busy} onClick={remove}>
                {t('Delete')}
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button>
            <Button busy={busy} disabled={!f.name || !f.taluka_id} onClick={save}>{t('Save')}</Button>
          </div>
        </div>
      }>
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Name (English) *')}><Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('नाव (Marathi)')}><Input value={f.name_mr || ''} onChange={(e) => setF({ ...f, name_mr: e.target.value })} /></Field>
        <Field label={t('Taluka *')}><TalukaSelect value={f.taluka_id} onChange={(v) => setF({ ...f, taluka_id: v })} placeholder={t('Select taluka')} /></Field>
        <Field label={t('PIN code')}><Input value={f.pin_code || ''} onChange={(e) => setF({ ...f, pin_code: e.target.value })} /></Field>
        <Field label={t('Latitude')}><Input type="number" step="any" value={f.lat} onChange={(e) => setF({ ...f, lat: e.target.value })} /></Field>
        <Field label={t('Longitude')}><Input type="number" step="any" value={f.lng} onChange={(e) => setF({ ...f, lng: e.target.value })} /></Field>
        <Field label={t('Status')}><Select options={['active', 'inactive']} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} /></Field>
      </div>
      <Field label={t('Hamlets (comma separated)')}><Input value={f.hamlets || ''} onChange={(e) => setF({ ...f, hamlets: e.target.value })} /></Field>
      <Field label={t('Alternate spellings (used by data import)')}><Input value={f.aliases || ''} onChange={(e) => setF({ ...f, aliases: e.target.value })} /></Field>
    </Modal>
  )
}

function Talukas() {
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const { data, reload } = useFetch('/talukas', { include_inactive: true })
  const [f, setF] = useState({ name: '', name_mr: '', district: 'Parbhani' })
  const { busy, error, run } = useAction()
  const add = () => run(async () => { await api.post('/talukas', f); invalidateRefData(); setF({ name: '', name_mr: '', district: f.district }); reload() }).catch(() => {})
  const deleteTaluka = async (row) => {
    if (!window.confirm(t('Are you sure you want to delete taluka {name}?', { name: row.name }))) return
    try {
      await api.delete(`/talukas/${row.id}`)
      invalidateRefData()
      reload()
    } catch (e) {
      alert(e.response?.data?.detail || e.message)
    }
  }
  return (
    <Card title={t('Talukas & districts')}>
      <ErrorBox message={error} />
      <div className="mb-4 grid gap-2 sm:grid-cols-4">
        <Input placeholder={t('Taluka name')} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <Input placeholder="तालुका" value={f.name_mr} onChange={(e) => setF({ ...f, name_mr: e.target.value })} />
        <Input placeholder={t('District')} value={f.district} onChange={(e) => setF({ ...f, district: e.target.value })} />
        <Button busy={busy} disabled={!f.name || !f.district} onClick={add}>{t('Add taluka')}</Button>
      </div>
      <Table columns={[
        { key: 'name', label: t('Taluka'), className: 'font-medium' }, { key: 'name_mr', label: 'तालुका' }, { key: 'district', label: t('District') },
        { key: 'village_count', label: t('Villages'), className: 'tabular text-right' }, { key: 'is_active', label: t('Status'), render: (row) => <StatusBadge value={row.is_active ? 'active' : 'inactive'} /> },
        ...(isSuperAdmin ? [{
          key: 'del', label: '', render: (row) => (
            <Button size="sm" variant="ghost" className="text-red-600 hover:text-red-800" icon={Trash2} onClick={() => deleteTaluka(row)} />
          )
        }] : []),
      ]} rows={data} />
    </Card>
  )
}

function GroupModal({ group, onClose, onSaved }) {
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const [f, setF] = useState(group ? { ...group, ...(group.meeting_schedule || {}) } : { group_type: 'kishori', frequency: 'monthly' })
  const { busy, error, run } = useAction()
  const save = () => run(async () => {
    const schedule = { frequency: f.frequency || 'monthly', day_of_week: f.day_of_week !== '' && f.day_of_week != null ? Number(f.day_of_week) : null, time: f.time || null, notes: f.notes || null }
    const body = { name: f.name, group_number: f.group_number || null, meeting_schedule: schedule, responsible_volunteer_id: f.responsible_volunteer_id || null }
    if (group) await api.patch(`/groups/${group.id}`, body)
    else await api.post('/groups', { ...body, group_type: f.group_type, village_id: f.village_id })
    onSaved()
  }).catch(() => {})

  const remove = () => run(async () => {
    if (!window.confirm(t('Are you sure you want to delete group {name}?', { name: group.name }))) return
    await api.delete(`/groups/${group.id}`)
    onSaved()
  }).catch(() => {})

  return (
    <Modal open title={group ? t('Edit {code}', { code: group.name }) : t('Add group')} onClose={onClose}
      footer={
        <div className="flex w-full items-center justify-between">
          <div>
            {group && isSuperAdmin && (
              <Button variant="danger" icon={Trash2} busy={busy} onClick={remove}>
                {t('Delete')}
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button>
            <Button busy={busy} disabled={!f.name || !f.village_id} onClick={save}>{t('Save')}</Button>
          </div>
        </div>
      }>
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Group name *')}><Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('Group number')}><Input value={f.group_number || ''} onChange={(e) => setF({ ...f, group_number: e.target.value })} /></Field>
        {!group && <Field label={t('Type')}><Select options={[{ value: 'kishori', label: t('Kishori group') }, { value: 'bal_panchayat', label: t('Bal Panchayat') }]} value={f.group_type} onChange={(e) => setF({ ...f, group_type: e.target.value })} /></Field>}
        {!group && <Field label={t('Village *')}><VillageSelect value={f.village_id} onChange={(v) => setF({ ...f, village_id: v })} placeholder={t('Select')} /></Field>}
        <Field label={t('Responsible volunteer')}><VolunteerSelect villageId={f.village_id} value={f.responsible_volunteer_id} onChange={(v) => setF({ ...f, responsible_volunteer_id: v })} placeholder={t('None')} /></Field>
        <Field label={t('Meeting frequency')}><Select options={['weekly', 'fortnightly', 'monthly', 'custom']} value={f.frequency || 'monthly'} onChange={(e) => setF({ ...f, frequency: e.target.value })} /></Field>
        <Field label={t('Meeting day')}><Select options={['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, i) => ({ value: String(i), label: d }))} placeholder="—" value={f.day_of_week ?? ''} onChange={(e) => setF({ ...f, day_of_week: e.target.value })} /></Field>
        <Field label={t('Meeting time')}><Input type="time" value={f.time || ''} onChange={(e) => setF({ ...f, time: e.target.value })} /></Field>
      </div>
    </Modal>
  )
}

function Groups() {
  const { user } = useAuth()
  const canAddGroup = user?.role === 'super_admin' || user?.role === 'admin_1' || user?.role === 'stakeholder'
  const [f, setF] = useState({ village_id: '', group_type: '' })
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const villages = useVillages()
  const vname = (id) => localName(villages.find((v) => v.id === id)) || '—'
  const { data, reload } = useFetch('/groups', { ...f, page, page_size: 50 })
  return (
    <Card padded={false} title={t('Kishori & Bal Panchayat groups')} actions={<>
      <VillageSelect value={f.village_id} onChange={(v) => { setF({ ...f, village_id: v }); setPage(1) }} />
      <Select options={[{ value: 'kishori', label: t('Kishori') }, { value: 'bal_panchayat', label: t('Bal Panchayat') }]} placeholder={t('All types')} value={f.group_type} onChange={(e) => { setF({ ...f, group_type: e.target.value }); setPage(1) }} />
      {canAddGroup && <Button size="sm" icon={Plus} onClick={() => setModal('new')}>{t('Add group')}</Button>}
    </>}>
      {!data ? <Spinner /> : (
        <>
          <Table onRowClick={setModal} columns={[
            { key: 'group_number', label: '#' }, { key: 'name', label: t('Group'), className: 'font-medium' },
            { key: 'group_type', label: t('Type'), render: (g) => <Badge tone={g.group_type === 'kishori' ? 'brand' : 'blue'}>{g.group_type === 'kishori' ? t('Kishori') : t('Bal Panchayat')}</Badge> },
            { key: 'village', label: t('Village'), render: (g) => vname(g.village_id) },
            { key: 'meeting', label: t('Meets'), render: (g) => g.meeting_schedule?.frequency || '—' },
            { key: 'vol', label: t('Volunteer'), render: (g) => (g.responsible_volunteer_id ? t('Assigned') : '—') },
          ]} rows={data.items} />
          <Pagination page={page} pageSize={50} total={data.total} onPage={setPage} />
        </>
      )}
      {modal && <GroupModal group={modal === 'new' ? null : modal} onClose={() => setModal(null)} onSaved={() => { setModal(null); reload() }} />}
    </Card>
  )
}

export function Locations() {
  const villages = useVillages()
  const [rows, setRows] = useState({})
  const [msg, setMsg] = useState(null)
  const { busy, error, run } = useAction()
  const set = (id, k, v) => setRows({ ...rows, [id]: { ...(rows[id] || {}), [k]: v } })
  const save = () => run(async () => {
    const items = Object.entries(rows)
      .map(([village_id, r]) => {
        const v = villages.find((x) => x.id === village_id)
        const lat = r.lat ?? v.location?.lat
        const lng = r.lng ?? v.location?.lng
        return { village_id, lat: Number(lat), lng: Number(lng), pin_code: (r.pin_code ?? v.pin_code) || null }
      })
      .filter((x) => !Number.isNaN(x.lat) && !Number.isNaN(x.lng) && x.lat && x.lng)
    if (!items.length) return
    const r = await api.put('/villages/locations', { items })
    invalidateRefData()
    setMsg(t('Saved {n} village(s). Reload the page to see them on the dashboard map.', { n: r.data.updated }))
    setRows({})
  }).catch(() => {})
  return (
    <Card title={t('Set village coordinates & PIN codes')} actions={<Button size="sm" busy={busy} onClick={save}>{t('Save changes')}</Button>}>
      <ErrorBox message={error} />
      {msg && <p className="mb-2 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-900">{msg}</p>}
      <p className="mb-3 text-xs text-gray-500">{t('Tip: in Google Maps, right-click a village centre and click the coordinates to copy “lat, lng”, then paste into Latitude.')}</p>
      <Table columns={[
        { key: 'name', label: t('Village'), render: (v) => <span className="font-medium">{v.name}</span> },
        { key: 'lat', label: t('Latitude (or paste "lat, lng")'), render: (v) => <Input type="text" value={rows[v.id]?.lat ?? v.location?.lat ?? ''} onChange={(e) => {
          const m = e.target.value.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/)
          if (m) setRows((p) => ({ ...p, [v.id]: { ...(p[v.id] || {}), lat: m[1], lng: m[2] } }))
          else set(v.id, 'lat', e.target.value)
        }} /> },
        { key: 'lng', label: t('Longitude'), render: (v) => <Input type="text" value={rows[v.id]?.lng ?? v.location?.lng ?? ''} onChange={(e) => set(v.id, 'lng', e.target.value)} /> },
        { key: 'pin', label: t('PIN'), render: (v) => <Input type="text" defaultValue={v.pin_code || ''} onChange={(e) => set(v.id, 'pin_code', e.target.value)} /> },
      ]} rows={villages} />
    </Card>
  )
}

export default function MasterData() {
  const [tab, setTab] = useState('groups')
  return (
    <div>
      <PageHeader title={t('Groups & talukas')} subtitle={t('Kishori / Bal Panchayat groups and the taluka–district hierarchy')} />
      <Tabs tabs={['groups', 'talukas']} value={tab} onChange={setTab} />
      {tab === 'groups' && <Groups />}
      {tab === 'talukas' && <Talukas />}
    </div>
  )
}
