import { Plus } from 'lucide-react'
import { useState } from 'react'
import { GroupMultiSelect, VillageSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Select, Spinner, Table } from '../components/ui'
import api from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtDateTime } from '../lib/format'
import { invalidateRefData, useAction, useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

function CreateUser({ open, onClose, onSaved }) {
  const [f, setF] = useState({ role: 'volunteer', group_ids: [] })
  const { busy, error, run } = useAction()
  const submit = () => run(async () => {
    await api.post('/users', {
      name: f.name, phone: f.phone || null, email: f.email || null, password: f.password, role: f.role,
      village_id: f.role === 'volunteer' ? f.village_id || null : null, group_ids: f.role === 'volunteer' ? f.group_ids : [],
    })
    invalidateRefData()
    onSaved()
  }).catch(() => {})
  return (
    <Modal open={open} title={t('Create user')} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} onClick={submit}>{t('Create')}</Button></>}>
      <ErrorBox message={error} />
      <Field label={t('Role')}>
        <Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} options={[
          { value: 'volunteer', label: t('Volunteer — field worker (multi-village)') },
          { value: 'admin_1', label: t('Admin-1 — events, groups, and field management') },
          { value: 'admin_2', label: t('Admin-2 — read-only monitor over volunteers') },
          { value: 'super_admin', label: t('Super Admin — complete authority over everything') },
        ]} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Name *')}><Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('Mobile (login; can be added later)')}><Input value={f.phone || ''} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label={t('Email')}><Input type="email" value={f.email || ''} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label={t('Initial password * (min 8)')}><Input type="password" value={f.password || ''} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
      </div>
      {f.role === 'volunteer' && (
        <>
          <Field label={t('Village (optional — can be assigned later)')}><VillageSelect value={f.village_id} onChange={(v) => setF({ ...f, village_id: v, group_ids: [] })} placeholder={t('Not assigned yet')} /></Field>
          <Field label={t('Kishori Groups')} group><GroupMultiSelect villageId={f.village_id} value={f.group_ids} onChange={(v) => setF({ ...f, group_ids: v })} /></Field>
        </>
      )}
    </Modal>
  )
}

function EditUser({ user, onClose, onSaved }) {
  const { user: me } = useAuth()
  const isSuperAdmin = me?.role === 'super_admin' || me?.role === 'stakeholder'
  const isReadOnly = me?.role === 'admin_2'
  const [f, setF] = useState({ name: user.name, phone: user.phone, email: user.email || '' })
  const [pwd, setPwd] = useState('')
  const [targetRole, setTargetRole] = useState(user.role)
  const [roleVillage, setRoleVillage] = useState('')
  const { busy, error, run } = useAction()
  const save = () => run(async () => { await api.patch(`/users/${user.id}`, { ...f, email: f.email || null }); onSaved() }).catch(() => {})
  const toggleActive = () => run(async () => { await api.patch(`/users/${user.id}/status`, { is_active: !user.is_active }); invalidateRefData(); onSaved() }).catch(() => {})
  const resetPwd = () => run(async () => { await api.post(`/users/${user.id}/reset-password`, { new_password: pwd }); setPwd(''); onSaved() }).catch(() => {})
  const changeRole = () => run(async () => {
    await api.patch(`/users/${user.id}/role`, { role: targetRole, village_id: targetRole === 'volunteer' ? roleVillage || null : null })
    invalidateRefData()
    onSaved()
  }).catch(() => {})
  const self = me?.id === user.id
  const canEdit = isSuperAdmin || (self && !isReadOnly)
  const roleOptions = [
    { value: 'volunteer', label: t('Volunteer') },
    { value: 'admin_1', label: t('Admin-1') },
    { value: 'admin_2', label: t('Admin-2') },
    { value: 'super_admin', label: t('Super Admin') },
  ]

  return (
    <Modal open title={user.name} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button>{canEdit && <Button busy={busy} onClick={save}>{t('Save profile')}</Button>}</>}>
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Name')}><Input value={f.name} disabled={!canEdit} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('Mobile')}><Input value={f.phone} disabled={!canEdit} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label={t('Email')} className="sm:col-span-2"><Input value={f.email} disabled={!canEdit} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
      </div>
      <p className="text-xs text-gray-500">{t("To change a volunteer's village use Volunteers → Reassign village (keeps history).")}</p>
      {canEdit && (
        <div className="flex items-end gap-2 border-t border-gray-100 pt-3">
          <Field label={t('Reset password')} className="flex-1"><Input type="password" placeholder={t('New password (min 8)')} value={pwd} onChange={(e) => setPwd(e.target.value)} /></Field>
          <Button size="sm" variant="secondary" disabled={pwd.length < 8} busy={busy} onClick={resetPwd}>{t('Reset')}</Button>
        </div>
      )}
      {!self && isSuperAdmin && (
        <div className="space-y-3 border-t border-gray-100 pt-3">
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t('Change Role')} className="w-48">
              <Select options={roleOptions} value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
            </Field>
            {targetRole === 'volunteer' && user.role !== 'volunteer' && (
              <Field label={t('Village for Volunteer')} className="flex-1">
                <VillageSelect value={roleVillage} onChange={setRoleVillage} placeholder={t('Assign later')} />
              </Field>
            )}
            <Button size="sm" variant="secondary" busy={busy} disabled={targetRole === user.role} onClick={changeRole}>
              {t('Update Role')}
            </Button>
            <div className="flex-1" />
            <Button size="sm" variant={user.is_active ? 'danger' : 'primary'} busy={busy} onClick={toggleActive}>
              {user.is_active ? t('Deactivate') : t('Activate')}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

export default function Users() {
  const { user: me } = useAuth()
  const isSuperAdmin = me?.role === 'super_admin' || me?.role === 'stakeholder'
  const [f, setF] = useState({ role: '', is_active: '', q: '' })
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(null)
  const { data, error, loading, reload } = useFetch('/users', { ...f, page, page_size: 25 })
  return (
    <div>
      <PageHeader
        title={t('Users & roles')}
        subtitle={t('Roles: Super Admin (complete authority), Admin-1 (events & groups), Admin-2 (monitoring), and Volunteer (field operations)')}
        actions={isSuperAdmin && <Button icon={Plus} onClick={() => setCreating(true)}>{t('Create user')}</Button>}
      />
      
      {isSuperAdmin && (
        <Card title={t('Super Admin Oversight Monitor')} className="mb-4 border-purple-300 bg-purple-50/40">
          <p className="text-xs text-purple-900 mb-3">
            {t('As Super Admin, you have full authority across all system operations, data management, and user roles.')}
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
            <div className="rounded-lg bg-white p-3 border border-purple-200">
              <span className="text-xs text-gray-500 block">{t('Total Users')}</span>
              <span className="text-xl font-bold text-purple-950">{data?.total || 0}</span>
            </div>
            <div className="rounded-lg bg-white p-3 border border-purple-200">
              <span className="text-xs text-gray-500 block">{t('Super Admins')}</span>
              <span className="text-xl font-bold text-purple-700">
                {(data?.items || []).filter(u => u.role === 'super_admin' || u.role === 'stakeholder').length}
              </span>
            </div>
            <div className="rounded-lg bg-white p-3 border border-purple-200">
              <span className="text-xs text-gray-500 block">{t('Admin-1')}</span>
              <span className="text-xl font-bold text-brand-900">
                {(data?.items || []).filter(u => u.role === 'admin_1').length}
              </span>
            </div>
            <div className="rounded-lg bg-white p-3 border border-purple-200">
              <span className="text-xs text-gray-500 block">{t('Admin-2')}</span>
              <span className="text-xl font-bold text-amber-800">
                {(data?.items || []).filter(u => u.role === 'admin_2').length}
              </span>
            </div>
            <div className="rounded-lg bg-white p-3 border border-purple-200">
              <span className="text-xs text-gray-500 block">{t('Volunteers')}</span>
              <span className="text-xl font-bold text-emerald-800">
                {(data?.items || []).filter(u => u.role === 'volunteer').length}
              </span>
            </div>
          </div>
        </Card>
      )}

      <Card padded={false}>
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-3">
          <Input placeholder={t('Search name, mobile, email')} value={f.q} onChange={(e) => { setF({ ...f, q: e.target.value }); setPage(1) }} />
          <Select options={[{ value: 'volunteer', label: t('Volunteer') }, { value: 'admin_1', label: t('Admin-1') }, { value: 'admin_2', label: t('Admin-2') }, { value: 'super_admin', label: t('Super Admin') }]} placeholder={t('Any role')} value={f.role} onChange={(e) => { setF({ ...f, role: e.target.value }); setPage(1) }} />
          <Select options={[{ value: 'true', label: t('Active') }, { value: 'false', label: t('Inactive') }]} placeholder={t('Active & inactive')} value={f.is_active} onChange={(e) => { setF({ ...f, is_active: e.target.value }); setPage(1) }} />
        </div>
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <>
            <Table onRowClick={setEditing} columns={[
              { key: 'name', label: t('Name'), className: 'font-medium' },
              { key: 'role', label: t('Role'), render: (u) => {
                const tone = (u.role === 'super_admin' || u.role === 'stakeholder') ? 'purple' : u.role === 'admin_1' ? 'brand' : u.role === 'admin_2' ? 'amber' : 'blue'
                const label = (u.role === 'super_admin' || u.role === 'stakeholder') ? t('Super Admin') : u.role === 'admin_1' ? t('Admin-1') : u.role === 'admin_2' ? t('Admin-2') : t('Volunteer')
                return <Badge tone={tone}>{label}</Badge>
              } },
              { key: 'phone', label: t('Mobile') },
              { key: 'email', label: t('Email') },
              { key: 'is_active', label: t('Status'), render: (u) => (u.is_active ? <Badge tone="green">{t('Active')}</Badge> : <Badge>{t('Inactive')}</Badge>) },
              { key: 'last_login_at', label: t('Last login'), render: (u) => fmtDateTime(u.last_login_at) },
            ]} rows={data?.items} />
            <Pagination page={page} pageSize={25} total={data?.total} onPage={setPage} />
          </>
        )}
      </Card>
      <CreateUser key={String(creating)} open={creating} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload() }} />
      {editing && <EditUser user={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
    </div>
  )
}
