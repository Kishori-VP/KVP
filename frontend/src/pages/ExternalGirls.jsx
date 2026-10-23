import {
  Eye,
  Pencil,
  Plus,
  Search,
  Trash2,
  Users,
} from 'lucide-react'
import { useState } from 'react'
import {
  Badge,
  Button,
  Card,
  DefinitionList,
  Empty,
  ErrorBox,
  Field,
  Input,
  Modal,
  PageHeader,
  Pagination,
  Select,
  Spinner,
  StatusBadge,
  Table,
  Textarea,
} from '../components/ui'
import api, { errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtDate, humanize } from '../lib/format'
import { useAction, useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

const EDUCATION_OPTIONS = [
  { value: 'in_school', label: 'In School (शाळेत)' },
  { value: 'in_college', label: 'In College (महाविद्यालयात)' },
  { value: 'dropout', label: 'Dropout (शाळाबाह्य)' },
  { value: 'working', label: 'Working (कामकरी)' },
  { value: 'other', label: 'Other (इतर)' },
]

/** Modal to register or edit an external girl. */
function ExternalGirlModal({ girl, onClose, onSaved }) {
  const isEditing = Boolean(girl?.id)
  const [f, setF] = useState(
    girl || {
      name: '',
      phone: '',
      alt_phone: '',
      age: '',
      dob: '',
      location: '',
      guardian_name: '',
      guardian_relation: '',
      education_status: '',
      school_or_college: '',
      standard: '',
      status: 'active',
      notes: '',
    }
  )
  const { busy, error, run } = useAction()

  const save = () =>
    run(async () => {
      const payload = {
        name: f.name.trim(),
        phone: f.phone?.trim() || null,
        alt_phone: f.alt_phone?.trim() || null,
        age: f.age ? Number(f.age) : null,
        dob: f.dob || null,
        location: f.location?.trim() || null,
        guardian_name: f.guardian_name?.trim() || null,
        guardian_relation: f.guardian_relation?.trim() || null,
        education_status: f.education_status || null,
        school_or_college: f.school_or_college?.trim() || null,
        standard: f.standard?.trim() || null,
        status: f.status || 'active',
        notes: f.notes?.trim() || null,
      }
      if (isEditing) {
        await api.patch(`/external-girls/${girl.id}`, payload)
      } else {
        await api.post('/external-girls', payload)
      }
      onSaved()
    })

  return (
    <Modal
      open
      title={isEditing ? t('Edit external girl') : t('Register external girl')}
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('Cancel')}
          </Button>
          <Button
            busy={busy}
            disabled={!f.name?.trim()}
            onClick={save}
          >
            {isEditing ? t('Save changes') : t('Register girl')}
          </Button>
        </>
      }
    >
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Full name (मुलीचे नाव) *')}>
          <Input
            value={f.name || ''}
            placeholder={t('e.g. Pooja Patil')}
            onChange={(e) => setF({ ...f, name: e.target.value })}
          />
        </Field>
        <Field label={t('Mobile phone (मोबाईल नंबर)')} hint={t('Optional contact phone')}>
          <Input
            type="tel"
            value={f.phone || ''}
            placeholder="9876543210"
            onChange={(e) => setF({ ...f, phone: e.target.value })}
          />
        </Field>
        <Field label={t('Alternative phone')}>
          <Input
            type="tel"
            value={f.alt_phone || ''}
            placeholder={t('Optional')}
            onChange={(e) => setF({ ...f, alt_phone: e.target.value })}
          />
        </Field>
        <Field label={t('Location / Village / Town (गाव / शहर / पत्ता)')}>
          <Input
            value={f.location || ''}
            placeholder={t('e.g. Parbhani, Ward 4')}
            onChange={(e) => setF({ ...f, location: e.target.value })}
          />
        </Field>
        <Field label={t('Age (वय)')}>
          <Input
            type="number"
            min={5}
            max={40}
            value={f.age || ''}
            onChange={(e) => setF({ ...f, age: e.target.value })}
          />
        </Field>
        <Field label={t('Date of birth')}>
          <Input
            type="date"
            value={f.dob?.slice?.(0, 10) || ''}
            onChange={(e) => setF({ ...f, dob: e.target.value })}
          />
        </Field>
        <Field label={t('Parent / Guardian name (पालकाचे नाव)')}>
          <Input
            value={f.guardian_name || ''}
            placeholder={t('Father, mother or guardian')}
            onChange={(e) => setF({ ...f, guardian_name: e.target.value })}
          />
        </Field>
        <Field label={t('Guardian relation (नाते)')}>
          <Input
            value={f.guardian_relation || ''}
            placeholder={t('Father, Mother, Brother, etc.')}
            onChange={(e) => setF({ ...f, guardian_relation: e.target.value })}
          />
        </Field>
        <Field label={t('Education status')}>
          <Select
            options={EDUCATION_OPTIONS}
            placeholder={t('Select status')}
            value={f.education_status || ''}
            onChange={(e) => setF({ ...f, education_status: e.target.value })}
          />
        </Field>
        <Field label={t('Class / Standard / Year')}>
          <Input
            value={f.standard || ''}
            placeholder={t('e.g. 11th, FY BA')}
            onChange={(e) => setF({ ...f, standard: e.target.value })}
          />
        </Field>
        <Field label={t('School / College name')} className="sm:col-span-2">
          <Input
            value={f.school_or_college || ''}
            placeholder={t('Name of school, college or training institute')}
            onChange={(e) => setF({ ...f, school_or_college: e.target.value })}
          />
        </Field>
        <Field label={t('Status')}>
          <Select
            options={[
              { value: 'active', label: t('Active (सक्रिय)') },
              { value: 'follow_up', label: t('Needs Follow-up (पाठपुरावा आवश्यक)') },
              { value: 'closed', label: t('Closed / Inactive (बंद)') },
            ]}
            value={f.status}
            onChange={(e) => setF({ ...f, status: e.target.value })}
          />
        </Field>
        <Field label={t('Notes / Background')} className="sm:col-span-2">
          <Textarea
            rows={2}
            value={f.notes || ''}
            placeholder={t('Family situation, background, scholarship, etc.')}
            onChange={(e) => setF({ ...f, notes: e.target.value })}
          />
        </Field>
      </div>
    </Modal>
  )
}

/** Full profile modal for an external girl */
function GirlProfileModal({ girlId, onClose, onEditGirl }) {
  const { data: g, loading, error } = useFetch(`/external-girls/${girlId}`)

  if (loading && !g) {
    return (
      <Modal open title={t('Loading…')} onClose={onClose}>
        <Spinner />
      </Modal>
    )
  }

  if (error || !g) {
    return (
      <Modal open title={t('Error')} onClose={onClose}>
        <ErrorBox message={error || t('Could not load girl profile.')} />
      </Modal>
    )
  }

  return (
    <Modal
      open
      title={<span>{g.name} {g.phone && <span className="text-sm font-normal text-gray-500">· {g.phone}</span>}</span>}
      onClose={onClose}
      wide
      footer={
        <div className="flex w-full items-center justify-between gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t('Close')}
          </Button>
          <Button
            variant="secondary"
            icon={Pencil}
            onClick={() => {
              onClose()
              onEditGirl(g)
            }}
          >
            {t('Edit')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Profile Details */}
        <div className="grid gap-3 sm:grid-cols-2">
          <Card title={t('Profile details')}>
            <DefinitionList
              items={[
                [t('Name'), g.name],
                [t('Mobile phone'), g.phone || '—'],
                [t('Alternative phone'), g.alt_phone || '—'],
                [t('Age'), g.age ? `${g.age} yrs` : '—'],
                [t('Date of birth'), g.dob ? fmtDate(g.dob) : '—'],
                [t('Location'), g.location || '—'],
                [t('Status'), <StatusBadge key="status" value={g.status} />],
              ]}
            />
          </Card>

          <Card title={t('Education & Family')}>
            <DefinitionList
              items={[
                [t('Parent / Guardian'), g.guardian_name ? `${g.guardian_name} ${g.guardian_relation ? `(${g.guardian_relation})` : ''}` : '—'],
                [t('Education status'), g.education_status ? humanize(g.education_status) : '—'],
                [t('School / College'), g.school_or_college || '—'],
                [t('Class / Standard'), g.standard || '—'],
                [t('Total calls'), g.call_summary?.total_calls ?? 0],
                [t('Last call'), g.call_summary?.last_call_at ? fmtDate(g.call_summary.last_call_at) : '—'],
              ]}
            />
          </Card>
        </div>

        {g.notes && (
          <Card title={t('Background notes')}>
            <p className="whitespace-pre-wrap text-sm text-gray-700">{g.notes}</p>
          </Card>
        )}

        {/* Prior Calls Log (Records only) */}
        {g.recent_calls?.length > 0 && (
          <Card title={t('Call Records & Observations ({n})', { n: g.recent_calls.length })}>
            <div className="space-y-2.5">
              {g.recent_calls.map((call) => (
                <div
                  key={call.id}
                  className="rounded-xl border border-gray-100 bg-gray-50/70 p-3 text-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200/60 pb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-900">{fmtDate(call.call_date)}</span>
                      <Badge variant="brand">{humanize(call.purpose)}</Badge>
                      <StatusBadge value={call.status} />
                    </div>
                    <span className="text-xs text-gray-500">
                      {t('Caller')}: {call.caller_name || 'Tai'}
                    </span>
                  </div>

                  {call.risk_indicators &&
                    Object.entries(call.risk_indicators).some(([, v]) => Boolean(v)) && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {Object.entries(call.risk_indicators)
                          .filter(([, v]) => Boolean(v))
                          .map(([k]) => (
                            <Badge key={k} tone="red">
                              {humanize(k)}
                            </Badge>
                          ))}
                      </div>
                    )}

                  {call.observations && (
                    <div className="mt-2 text-xs">
                      <span className="font-semibold text-gray-600">{t('Observations')}:</span>
                      <p className="mt-0.5 whitespace-pre-wrap text-gray-800">{call.observations}</p>
                    </div>
                  )}

                  {call.notes && (
                    <div className="mt-1.5 text-xs">
                      <span className="font-semibold text-gray-600">{t('Notes / Next steps')}:</span>
                      <p className="mt-0.5 whitespace-pre-wrap text-gray-800">{call.notes}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </Modal>
  )
}

/** Main External Girls Directory Page (Pure Record View) */
export default function ExternalGirls() {
  const { user } = useAuth()

  // External girls list state
  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)

  // Modals state
  const [girlModal, setGirlModal] = useState(false) // false | 'new' | girl object for editing
  const [profileGirlId, setProfileGirlId] = useState(null) // id

  // Query external girls
  const girlsQuery = useFetch('/external-girls', {
    q: q || undefined,
    status: statusFilter || undefined,
    page,
    page_size: 25,
  })

  const refreshAll = () => {
    girlsQuery.reload()
  }

  const deleteGirl = async (girl) => {
    if (!window.confirm(t('Are you sure you want to delete {name}?', { name: girl.name }))) {
      return
    }
    try {
      await api.delete(`/external-girls/${girl.id}`)
      girlsQuery.reload()
    } catch (e) {
      alert(errorMessage(e))
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={t('External girls (बाह्य किशोरी)')}
        subtitle={t('Directory and records of girls and students outside regular village groups.')}
        actions={
          <Button
            icon={Plus}
            onClick={() => setGirlModal('new')}
          >
            {t('Register external girl')}
          </Button>
        }
      />

      <Card padded={false}>
        {/* Filters Bar */}
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-3">
          <div className="relative sm:col-span-2">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input
              className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-brand-500 focus:outline-none"
              placeholder={t('Search by girl name, phone, location, guardian…')}
              value={q}
              onChange={(e) => {
                setQ(e.target.value)
                setPage(1)
              }}
            />
          </div>
          <Select
            options={[
              { value: '', label: t('All statuses (सर्व स्थिती)') },
              { value: 'active', label: t('Active (सक्रिय)') },
              { value: 'follow_up', label: t('Needs Follow-up (पाठपुरावा)') },
              { value: 'closed', label: t('Closed (बंद)') },
            ]}
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
          />
        </div>

        <ErrorBox message={girlsQuery.error} />

        {girlsQuery.loading && !girlsQuery.data ? (
          <Spinner />
        ) : (
          <>
            <div className="px-3 pt-2 text-xs text-gray-500">
              {t('{n} girls', { n: girlsQuery.data?.total || 0 })}
            </div>
            <Table
              columns={[
                {
                  key: 'name',
                  label: t('Girl Name'),
                  className: 'font-medium',
                  render: (r) => (
                    <div>
                      <button
                        type="button"
                        className="text-left font-semibold text-brand-800 hover:underline"
                        onClick={() => setProfileGirlId(r.id)}
                      >
                        {r.name}
                      </button>
                      {r.name_en && r.name_en !== r.name && (
                        <div className="text-xs text-gray-400">{r.name_en}</div>
                      )}
                      {r.status === 'follow_up' && (
                        <Badge tone="yellow">{t('Follow-up')}</Badge>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'phone',
                  label: t('Mobile'),
                  render: (r) => (
                    <span className="font-mono text-xs">{r.phone || '—'}</span>
                  ),
                },
                {
                  key: 'age',
                  label: t('Age'),
                  render: (r) => (r.age ? `${r.age} yrs` : '—'),
                },
                {
                  key: 'location',
                  label: t('Location'),
                  render: (r) => r.location || '—',
                },
                {
                  key: 'guardian',
                  label: t('Guardian'),
                  render: (r) =>
                    r.guardian_name ? (
                      <span>
                        {r.guardian_name}
                        {r.guardian_relation ? ` (${r.guardian_relation})` : ''}
                      </span>
                    ) : (
                      '—'
                    ),
                },
                {
                  key: 'education',
                  label: t('Education / Course'),
                  render: (r) => (
                    <span className="line-clamp-1 text-xs">
                      {r.standard || (r.education_status ? humanize(r.education_status) : '—')}
                    </span>
                  ),
                },
                {
                  key: 'school',
                  label: t('School / College'),
                  render: (r) => (
                    <span className="line-clamp-1 text-xs text-gray-600">
                      {r.school_or_college || '—'}
                    </span>
                  ),
                },
                {
                  key: 'calls',
                  label: t('Calls Logged'),
                  render: (r) => (
                    <div className="text-xs">
                      <span className="font-semibold text-gray-800">
                        {t('{n} calls', { n: r.call_summary?.total_calls || 0 })}
                      </span>
                      {r.call_summary?.last_call_at && (
                        <div className="text-gray-500">
                          {fmtDate(r.call_summary.last_call_at)}
                        </div>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'actions',
                  label: '',
                  render: (r) => (
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={Eye}
                        title={t('View record details')}
                        onClick={() => setProfileGirlId(r.id)}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={Pencil}
                        title={t('Edit record')}
                        onClick={() => setGirlModal(r)}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={Trash2}
                        className="text-red-600 hover:text-red-800"
                        title={t('Delete record')}
                        onClick={() => deleteGirl(r)}
                      />
                    </div>
                  ),
                },
              ]}
              rows={girlsQuery.data?.items}
              empty={t('No external girls registered yet. Click "Register external girl" to add one.')}
            />
            <Pagination
              page={page}
              pageSize={25}
              total={girlsQuery.data?.total}
              onPage={setPage}
            />
          </>
        )}
      </Card>

      {/* Modals */}
      {girlModal && (
        <ExternalGirlModal
          girl={girlModal === 'new' ? null : girlModal}
          onClose={() => setGirlModal(false)}
          onSaved={() => {
            setGirlModal(false)
            refreshAll()
          }}
        />
      )}

      {profileGirlId && (
        <GirlProfileModal
          girlId={profileGirlId}
          onClose={() => setProfileGirlId(null)}
          onEditGirl={(g) => {
            setProfileGirlId(null)
            setGirlModal(g)
          }}
        />
      )}
    </div>
  )
}
