import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ChildModal from '../components/ChildModal'
import { Button, Card, ErrorBox, PageHeader, Spinner, Table } from '../components/ui'
import api from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtDate, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

export default function VolunteerGroupDetail() {
  const { id } = useParams()
  const { data, error, loading, reload } = useFetch(`/groups/${id}`)
  const { user } = useAuth()
  const nav = useNavigate()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const [childModal, setChildModal] = useState(null)
  const girlIds = new Set((data?.girls || []).map((g) => g.id))

  const deleteGroup = async () => {
    if (!window.confirm(t('Are you sure you want to delete this group? This cannot be undone.'))) return
    try {
      await api.delete(`/groups/${id}`)
      nav(-1)
    } catch (err) {
      alert(err?.response?.data?.detail || err.message || 'Failed to delete group')
    }
  }

  const deleteChild = async (memberId) => {
    if (!window.confirm(t('Are you sure you want to delete this member from the Bal Panchayat?'))) return
    try {
      await api.delete(`/children/${id}/${memberId}`)
      reload()
    } catch (err) {
      alert(err?.response?.data?.detail || err.message || 'Failed to delete member')
    }
  }

  if (loading && !data) return <Spinner />

  const isBalPanchayat = data?.group_type === 'bal_panchayat' || (data?.members && data.members.length > 0)

  return (
    <div className="space-y-4">
      {user?.role === 'volunteer'
        ? <Link to="/groups" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" />{t('My village groups')}</Link>
        : <button type="button" onClick={() => nav(-1)} className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" />{t('Back')}</button>}
      <ErrorBox message={error} />
      {data && (
        <>
          <PageHeader
            title={localName(data)}
            subtitle={`${humanize(data.group_type)}${data.group_number ? ` · ${data.group_number}` : ''}`}
            action={isSuperAdmin && (
              <Button variant="danger" icon={Trash2} onClick={deleteGroup}>
                {t('Delete group')}
              </Button>
            )}
          />

          <Card title={t('Group details')}>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div><span className="text-gray-500">{t('Meeting frequency')}</span><p className="font-medium">{humanize(data.meeting_schedule?.frequency || 'not set')}</p></div>
              <div><span className="text-gray-500">{t('Meeting time')}</span><p className="font-medium">{data.meeting_schedule?.time || '—'}</p></div>
              <div><span className="text-gray-500">{t('Girls registered')}</span><p className="font-medium">{data.girl_count || 0}</p></div>
              {data.member_count > 0 && <div><span className="text-gray-500">{t('Members')}</span><p className="font-medium">{data.member_count}</p></div>}
              <div><span className="text-gray-500">{t('Notes')}</span><p className="font-medium">{data.meeting_schedule?.notes || '—'}</p></div>
            </div>
          </Card>

          <Card title={t('Girls in this group')}>
            <Table
              columns={[
                { key: 'girl_code', label: t('Girl ID'), className: 'font-medium' },
                { key: 'name', label: t('Name'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/girls/${r.id}`}>{localName(r) || t('Not recorded')}</Link> },
                { key: 'dob', label: t('Date of birth'), render: (r) => fmtDate(r.dob) },
              ]}
              rows={data.girls || []}
              empty={t('No girls are currently linked to this group.')}
            />
          </Card>

          {isBalPanchayat && (
            <Card
              title={t('Bal Panchayat members')}
              action={isSuperAdmin && (
                <Button size="sm" icon={Plus} onClick={() => setChildModal({ group_id: id, village_id: data.village_id })}>
                  {t('Add member')}
                </Button>
              )}
            >
              <p className="mb-3 text-xs text-gray-500">
                {t('Every child in the Bal Panchayat, including boys. Registered girls link to their profile.')}
              </p>
              <Table
                columns={[
                  {
                    key: 'name',
                    label: t('Name'),
                    render: (m) => (m.girl_id && girlIds.has(m.girl_id)
                      ? <Link className="text-brand-700 hover:underline" to={`/girls/${m.girl_id}`}>{m.name}</Link>
                      : m.name),
                  },
                  {
                    key: 'gender',
                    label: t('Gender'),
                    render: (m) => (m.gender === 'girl' ? t('Girl (मुलगी)') : t('Boy (मुलगा)')),
                  },
                  { key: 'standard', label: t('Class'), render: (m) => m.standard || '—' },
                  { key: 'phone', label: t('Mobile'), render: (m) => m.phone || '—' },
                  ...(isSuperAdmin ? [{
                    key: 'actions',
                    label: '',
                    className: 'text-right',
                    render: (m) => {
                      const memberId = m.member_id || m.id || m.name
                      return (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            title={t('Edit')}
                            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-brand-700"
                            onClick={() => setChildModal({ ...m, group_id: id, member_id: memberId })}
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            title={t('Delete')}
                            className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                            onClick={() => deleteChild(memberId)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      )
                    },
                  }] : []),
                ]}
                rows={(data.members || []).map((m, i) => ({ ...m, id: m.id || m.member_id || `m_${i}` }))}
                empty={t('No Bal Panchayat members added yet.')}
              />
            </Card>
          )}

          {childModal && (
            <ChildModal
              child={childModal}
              defaultGroupId={id}
              defaultVillageId={data.village_id}
              onClose={() => setChildModal(null)}
              onSaved={() => {
                setChildModal(null)
                reload()
              }}
            />
          )}
        </>
      )}
    </div>
  )
}
