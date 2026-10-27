import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { GroupSelect, VillageSelect } from './pickers'
import { Button, ErrorBox, Field, Input, Modal, Select } from './ui'
import api from '../lib/api'
import { useAuth } from '../lib/auth'
import { useAction } from '../lib/hooks'
import { t } from '../lib/i18n'

export default function ChildModal({ child, defaultVillageId, defaultGroupId, onClose, onSaved }) {
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const editing = Boolean(child?.member_id || child?.id)
  const [villageId, setVillageId] = useState(child?.village?.id || child?.village_id || defaultVillageId || '')
  const [groupId, setGroupId] = useState(child?.group?.id || child?.group_id || defaultGroupId || '')
  const [f, setF] = useState({
    name: child?.name || '',
    standard: child?.standard || '',
    phone: child?.phone || '',
    gender: child?.gender || 'boy',
  })
  const { busy, error, run } = useAction()

  const save = () => run(async () => {
    if (!groupId) return
    const body = {
      name: f.name.trim(),
      standard: f.standard?.trim() || null,
      phone: f.phone?.trim() || null,
      gender: f.gender || 'boy',
    }
    if (editing) {
      const gId = child.group?.id || child.group_id || groupId
      const mId = child.member_id || child.id
      await api.patch(`/children/${gId}/${mId}`, body)
    } else {
      await api.post('/children', { ...body, group_id: groupId })
    }
    onSaved()
  }).catch(() => {})

  const remove = () => run(async () => {
    if (!window.confirm(t('Are you sure you want to delete this child from the Bal Panchayat?'))) return
    const gId = child.group?.id || child.group_id || groupId
    const mId = child.member_id || child.id
    await api.delete(`/children/${gId}/${mId}`)
    onSaved()
  }).catch(() => {})

  return (
    <Modal
      open
      title={editing ? t('Edit Child') : t('Add Child to Bal Panchayat')}
      onClose={onClose}
      footer={
        <div className="flex w-full items-center justify-between">
          <div>
            {editing && isSuperAdmin && (
              <Button variant="danger" busy={busy} icon={Trash2} onClick={remove}>
                {t('Delete')}
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button>
            <Button busy={busy} disabled={!f.name.trim() || !groupId} onClick={save}>
              {editing ? t('Save changes') : t('Add Child')}
            </Button>
          </div>
        </div>
      }
    >
      <ErrorBox message={error} />
      <div className="space-y-3">
        {!editing && !defaultGroupId && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('Village *')}>
              <VillageSelect value={villageId} onChange={(v) => { setVillageId(v); setGroupId('') }} placeholder={t('Select village')} />
            </Field>
            <Field label={t('Bal Panchayat *')}>
              <GroupSelect villageId={villageId} groupType="bal_panchayat" value={groupId} onChange={setGroupId} placeholder={t('Select Bal Panchayat')} />
            </Field>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t('Child Full Name *')}>
            <Input value={f.name} placeholder={t('e.g. Rohan Pawar')} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label={t('Gender')}>
            <Select
              options={[{ value: 'boy', label: t('Boy (मुलगा)') }, { value: 'girl', label: t('Girl (मुलगी)') }]}
              value={f.gender}
              onChange={(e) => setF({ ...f, gender: e.target.value })}
            />
          </Field>
          <Field label={t('Class / Standard')}>
            <Input value={f.standard} placeholder={t('e.g. 7th')} onChange={(e) => setF({ ...f, standard: e.target.value })} />
          </Field>
          <Field label={t('Mobile number')}>
            <Input type="tel" value={f.phone} placeholder="9876543210" onChange={(e) => setF({ ...f, phone: e.target.value })} />
          </Field>
        </div>
      </div>
    </Modal>
  )
}
