import { ArrowLeft, MessageCircle, Pencil, Phone, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, DefinitionList, ErrorBox, PageHeader, Spinner, Table } from '../components/ui'
import api from '../lib/api'
import { useAuth } from '../lib/auth'
import { humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { localName, t } from '../lib/i18n'
import { VillageModal } from './MasterData'

export default function VillageDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const [editing, setEditing] = useState(false)
  const { data: v, error, reload } = useFetch(`/villages/${id}`)

  const deleteVillage = async () => {
    if (!window.confirm(t('Are you sure you want to delete {name}?', { name: localName(v) }))) return
    try {
      await api.delete(`/villages/${id}`)
      nav('/villages')
    } catch (e) {
      alert(e.response?.data?.detail || e.message)
    }
  }

  if (error) return <ErrorBox message={error} />
  if (!v) return <Spinner />

  return (
    <div className="space-y-4">
      <Link to="/villages" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" /> {t('Villages')}</Link>
      <PageHeader
        title={localName(v)}
        subtitle={`${v.taluka?.name} ${t('taluka')} · ${v.district} ${t('district')}`}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" icon={Pencil} onClick={() => setEditing(true)}>
              {t('Edit')}
            </Button>
            {isSuperAdmin && (
              <Button variant="danger" icon={Trash2} onClick={deleteVillage}>
                {t('Delete village')}
              </Button>
            )}
          </div>
        }
      />
      {v.missing_mandatory_contacts.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t('Missing key contacts')}: {v.missing_mandatory_contacts.map(humanize).join(', ')} — {t('add them under')} <Link className="underline" to="/contacts">{t('Contacts')}</Link>.
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t('Village')}>
          <DefinitionList items={[
            ['Girls', v.girl_count], ['Girls without a group', v.girls_without_group], ['PIN code', v.pin_code],
            ['Coordinates', v.location ? `${v.location.lat}, ${v.location.lng}` : t('Not set')], ['Hamlets', (v.hamlets || []).join(', ')],
          ]} />
        </Card>
        <Card title={t('Volunteers')}>
          <Table columns={[
            { key: 'name', label: t('Name'), render: (u) => <Link className="text-brand-700 hover:underline" to={`/volunteers/${u.id}`}>{u.name}</Link> },
            { key: 'phone', label: t('Mobile') },
            { key: 'is_active', label: '', render: (u) => (!u.is_active ? <Badge>{t('Inactive')}</Badge> : null) },
          ]} rows={v.volunteers} empty={t('No volunteer assigned.')} />
        </Card>
        <Card title={t('Groups')}>
          <Table columns={[
            { key: 'name', label: t('Group'), render: (g) => <Link className="text-brand-700 hover:underline" to={`/groups/${g.id}`}>{localName(g)}</Link> },
            { key: 'group_type', label: t('Type'), render: (g) => (g.group_type === 'kishori' ? t('Kishori') : t('Bal Panchayat')) },
            { key: 'girl_count', label: t('Girls'), className: 'tabular text-right' },
            { key: 'member_count', label: t('Members'), className: 'tabular text-right', render: (g) => g.member_count || '—' },
          ]} rows={v.groups} />
        </Card>
        <Card title={t('Key contacts')}>
          <Table columns={[
            { key: 'category', label: t('Role'), render: (c) => humanize(c.category) },
            { key: 'name', label: t('Name') },
            { key: 'mobile', label: t('Mobile'), render: (c) => (
              <span className="inline-flex items-center gap-2">{c.mobile}
                {c.quick_actions && <><a href={c.quick_actions.call} title={t('Call')}><Phone className="h-4 w-4 text-brand-700" /></a><a href={c.quick_actions.whatsapp} target="_blank" rel="noreferrer" title={t('WhatsApp')}><MessageCircle className="h-4 w-4 text-green-700" /></a></>}
              </span>) },
            { key: 'verified', label: '', render: (c) => (c.verified ? <Badge tone="green">{t('Verified')}</Badge> : <Badge tone="yellow">{t('Unverified')}</Badge>) },
          ]} rows={v.contacts} empty={t('No contacts yet.')} />
        </Card>
      </div>

      {editing && (
        <VillageModal
          village={v}
          onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); reload() }}
        />
      )}
    </div>
  )
}
