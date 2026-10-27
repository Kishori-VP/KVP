import { FileText, ImagePlus, Plus, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GroupSelect, LookupSelect, TalukaSelect, VillageSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Select, Spinner, StatusBadge, Table } from '../components/ui'
import { AADHAAR_SIDES, uploadAadhaar } from '../lib/aadhaar'
import api, { errorMessage } from '../lib/api'
import { fmtDate, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { useAuth } from '../lib/auth'
import { casteLabel, categoryLabel, locale, localName, t } from '../lib/i18n'

/** File picker with a thumbnail preview, used for each side of the Aadhaar card. */
function AadhaarPicker({ label, file, onChange }) {
  const preview = useMemo(() => (file?.type.startsWith('image/') ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview])
  const shown = preview
  return (
    <div>
      <div className="mb-1 text-sm font-medium text-gray-700">{t(label)}</div>
      <label className="relative flex h-36 cursor-pointer items-center justify-center overflow-hidden rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 text-sm text-gray-500 hover:border-brand-400 hover:bg-brand-50/40">
        {shown ? (
          <img src={shown} alt={t(label)} className="h-full w-full object-contain" />
        ) : file ? (
          <span className="flex items-center gap-1.5 px-3 text-center"><FileText className="h-5 w-5 shrink-0" /> {file.name}</span>
        ) : (
          <span className="flex flex-col items-center gap-1"><ImagePlus className="h-6 w-6" /> {t('Choose photo or PDF')}</span>
        )}
        <input type="file" accept="image/*,application/pdf" className="sr-only" onChange={(e) => { onChange(e.target.files[0] || null); e.target.value = '' }} />
      </label>
      {file && (
        <button type="button" className="mt-1 inline-flex items-center gap-1 text-xs text-gray-500 hover:text-red-700" onClick={() => onChange(null)}>
          <X className="h-3 w-3" /> {t('Remove')}
        </button>
      )}
    </div>
  )
}

const EMPTY = { q: '', taluka_id: '', village_id: '', group_id: '', school_status: '', age_band: '', participation: '', case_status: '', anaemia: '', profile_incomplete: '' }

export function GirlForm({ initial, onSaved, onCancel }) {
  const { user } = useAuth()
  const [f, setF] = useState(initial || { household: {}, village_id: user?.role === 'volunteer' ? (user.village_id || user?.villages?.[0]?.id || '') : '' })
  const [error, setError] = useState(null)
  const [dupes, setDupes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [aadhaar, setAadhaar] = useState({})
  const [saved, setSaved] = useState(null)
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }))
  const setH = (k, v) => setF((p) => ({ ...p, household: { ...(p.household || {}), [k]: v } }))
  const editing = Boolean(initial?.id)

  const save = async (confirm = false) => {
    setBusy(true)
    setError(null)
    const body = {
      name: f.name || null, dob: f.dob || null, age: f.age ? Number(f.age) : null, village_id: f.village_id,
      group_id: f.group_id || null, school_status: f.school_status || null, school_name: f.school_name || null,
      standard: f.standard || null, phone: f.phone || null,
      household: Object.fromEntries(Object.entries(f.household || {}).filter(([, v]) => v !== '' && v !== null)),
    }
    if (body.household.members_count) body.household.members_count = Number(body.household.members_count)
    try {
      const r = editing
        ? await api.patch(`/girls/${initial.id}`, body)
        : await api.post('/girls', { ...body, confirm_not_duplicate: confirm })
      setSaved(r.data)
      const failed = []
      for (const { kind, label } of AADHAAR_SIDES) {
        if (!aadhaar[kind]) continue
        try {
          await uploadAadhaar(r.data.id, kind, aadhaar[kind])
        } catch (e) {
          failed.push(`${t(label)}: ${errorMessage(e)}`)
        }
      }
      if (failed.length) setError(`${t('The girl was saved, but the Aadhaar upload failed. You can upload it again from her profile.')} ${failed.join(' · ')}`)
      else onSaved(r.data)
    } catch (e) {
      if (e.response?.status === 409 && e.response.data?.detail?.candidates) setDupes(e.response.data.detail.candidates)
      else setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <ErrorBox message={error} />
      {dupes && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
          <p className="mb-2 font-medium text-amber-900">{t('Possible duplicates found — check before saving:')}</p>
          <ul className="mb-2 space-y-1">
            {dupes.map((d) => (
              <li key={d.girl.id} className="flex justify-between gap-2">
                <a className="text-brand-700 hover:underline" href={`/girls/${d.girl.id}`} target="_blank" rel="noreferrer">
                  {d.girl.girl_code} · {localName(d.girl) || t('no name')}
                </a>
                <span className="text-amber-800">{t('{n}% match', { n: Math.round(d.score * 100) })}</span>
              </li>
            ))}
          </ul>
          <Button size="sm" variant="secondary" busy={busy} onClick={() => save(true)}>{t('Not a duplicate — save anyway')}</Button>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Full name (मुलीचे नाव) *')}><Input value={f.name || ''} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label={t('Village *')}>
          {user?.role === 'volunteer' ? (
            user?.villages?.length > 1 ? (
              <select
                value={f.village_id || user.villages[0]?.id || ''}
                onChange={(e) => { set('village_id', e.target.value); set('group_id', '') }}
                className="w-full rounded-lg border border-gray-300 p-2 text-sm focus:border-brand-500 focus:outline-none"
              >
                {user.villages.map((v) => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            ) : (
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                {user?.village?.name || t('Assigned village only')}
              </div>
            )
          ) : (
            <VillageSelect value={f.village_id} onChange={(v) => { set('village_id', v); set('group_id', '') }} placeholder={t('Select village')} />
          )}
        </Field>
        <Field label={t('Kishori Group')}><GroupSelect villageId={f.village_id} value={f.group_id} onChange={(v) => set('group_id', v)} placeholder={t('No group')} /></Field>
        <Field label={t('School status')}><LookupSelect type="school_status" value={f.school_status} onChange={(v) => set('school_status', v)} placeholder={t('Unknown')} /></Field>
        <Field label={t('Date of birth')} hint={t('Or give age if DOB is unknown')}><Input type="date" value={f.dob?.slice?.(0, 10) || ''} onChange={(e) => set('dob', e.target.value)} /></Field>
        <Field label={t('Age (years)')}><Input type="number" min={5} max={30} value={f.age || ''} onChange={(e) => set('age', e.target.value)} /></Field>
        <Field label={t('School name')}><Input value={f.school_name || ''} onChange={(e) => set('school_name', e.target.value)} /></Field>
        <Field label={t('Class / standard')}><Input value={f.standard || ''} onChange={(e) => set('standard', e.target.value)} /></Field>
      </div>
      <div className="pt-1 text-xs font-semibold uppercase tracking-wide text-gray-500">{t('Household')}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("Father's name")}><Input value={f.household?.father_name || ''} onChange={(e) => setH('father_name', e.target.value)} /></Field>
        <Field label={t("Mother's name")}><Input value={f.household?.mother_name || ''} onChange={(e) => setH('mother_name', e.target.value)} /></Field>
        <Field label={t('Head of household')}><Input value={f.household?.head_name || ''} onChange={(e) => setH('head_name', e.target.value)} /></Field>
        <Field label={t('Family mobile')} hint={t('Used for event SMS reminders')}><Input value={f.household?.phone || ''} onChange={(e) => setH('phone', e.target.value)} /></Field>
        <Field label={t('Members')}><Input type="number" min={1} value={f.household?.members_count || ''} onChange={(e) => setH('members_count', e.target.value)} /></Field>
        <Field label={t('Economic status')}><Select options={['bpl', 'apl', 'unknown']} placeholder="—" value={f.household?.economic_status || ''} onChange={(e) => setH('economic_status', e.target.value)} /></Field>
        <Field label={t('Address / hamlet')} className="sm:col-span-2"><Input value={f.household?.address || ''} onChange={(e) => setH('address', e.target.value)} /></Field>
      </div>
      <div className="pt-1 text-xs font-semibold uppercase tracking-wide text-gray-500">{t('Aadhaar card')}</div>
      {editing && <p className="text-xs text-gray-500">{t('Choose a file only to replace the one already uploaded.')}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        {AADHAAR_SIDES.map(({ kind, label }) => (
          <AadhaarPicker key={kind} label={label} file={aadhaar[kind]} onChange={(file) => setAadhaar((p) => ({ ...p, [kind]: file }))} />
        ))}
      </div>
      <div className="flex justify-end gap-2 pt-2">
        {saved ? (
          <Button onClick={() => onSaved(saved)}>{editing ? t('Close') : t('Open profile')}</Button>
        ) : (
          <>
            {onCancel && <Button variant="secondary" onClick={onCancel}>{t('Cancel')}</Button>}
            <Button busy={busy} onClick={() => save(false)} disabled={!f.village_id || !f.name}>{editing ? t('Save changes') : t('Register girl')}</Button>
          </>
        )}
      </div>
    </div>
  )
}

/** Drop columns that have no value on any row of the page; a column's `value` also serves as its cell text. */
function visibleColumns(rows, columns) {
  const filled = (v) => v !== undefined && v !== null && v !== '' && v !== false && v !== 0
  return columns
    .filter((col) => col.always || (rows || []).some((r) => filled(col.value(r))))
    .map((col) => (!col.value ? col : { ...col, render: (r) => (filled(col.value(r)) ? (col.render ? col.render(r) : col.value(r)) : '—') }))
}

export default function Girls() {
  const nav = useNavigate()
  const { user } = useAuth()
  const canCreate = user?.role === 'volunteer' || user?.role === 'super_admin' || user?.role === 'stakeholder'
  const [filters, setFilters] = useState(() => user?.role === 'volunteer' ? { ...EMPTY, village_id: user.village_id || '' } : EMPTY)
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const set = (k, v) => { setFilters((p) => ({ ...p, [k]: v, ...(k === 'village_id' ? { group_id: '' } : {}) })); setPage(1) }
  const { data, error, loading } = useFetch('/girls', { ...filters, page, page_size: 25 })

  return (
    <div>
      <PageHeader title={t('Girls (beneficiaries)')} subtitle={t('Unique Girl IDs, profiles and participation')} actions={canCreate ? <Button icon={Plus} onClick={() => setCreating(true)}>{t('Register girl')}</Button> : null} />
      <Card padded={false}>
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="relative lg:col-span-2">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm" placeholder={t('Search name, Girl ID, parent…')} value={filters.q} onChange={(e) => set('q', e.target.value)} />
          </div>
          {user?.role !== 'volunteer' && <TalukaSelect value={filters.taluka_id} onChange={(v) => set('taluka_id', v)} />}
          {user?.role !== 'volunteer' && <VillageSelect value={filters.village_id} talukaId={filters.taluka_id} onChange={(v) => set('village_id', v)} />}
          <GroupSelect villageId={filters.village_id} value={filters.group_id} onChange={(v) => set('group_id', v)} />
          <LookupSelect type="school_status" value={filters.school_status} onChange={(v) => set('school_status', v)} placeholder={t('Any school status')} />
          <Select options={[{ value: '10_14', label: t('Age 10–14') }, { value: '15_19', label: t('Age 15–19') }, { value: 'below_10', label: t('Below 10') }, { value: '20_plus', label: '20+' }]} placeholder={t('Any age')} value={filters.age_band} onChange={(e) => set('age_band', e.target.value)} />
          <Select options={[{ value: 'active', label: t('Participated (90 days)') }, { value: 'inactive', label: t('Not in 90 days') }, { value: 'never', label: t('Never participated') }]} placeholder={t('Any participation')} value={filters.participation} onChange={(e) => set('participation', e.target.value)} />
          <Select options={[{ value: 'open', label: t('Has open case') }, { value: 'none', label: t('No cases') }, 'resolved', 'closed', 'escalated']} placeholder={t('Any case status')} value={filters.case_status} onChange={(e) => set('case_status', e.target.value)} />
          <Select options={['severe', 'moderate', 'mild', 'normal', 'unscreened']} placeholder={t('Any anaemia status')} value={filters.anaemia} onChange={(e) => set('anaemia', e.target.value)} />
          <Select options={[{ value: 'true', label: t('Incomplete profiles') }, { value: 'false', label: t('Complete profiles') }]} placeholder={t('Any profile')} value={filters.profile_incomplete} onChange={(e) => set('profile_incomplete', e.target.value)} />
        </div>
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <>
            <div className="px-3 pt-2 text-xs text-gray-500">{t('{n} girls', { n: data?.total?.toLocaleString(locale()) })}</div>
            <Table
              onRowClick={(r) => nav(`/girls/${r.id}`)}
              columns={visibleColumns(data?.items, [
                { key: 'girl_code', label: t('Girl ID'), className: 'whitespace-nowrap font-medium', always: true },
                { key: 'name', label: t('Name'), always: true, render: (r) => localName(r) || <span className="text-gray-400">{t('Not recorded')}</span> },
                { key: 'current_age', label: t('Age'), value: (r) => r.current_age },
                { key: 'dob', label: t('Date of birth'), className: 'whitespace-nowrap', value: (r) => r.dob, render: (r) => fmtDate(r.dob) },
                { key: 'standard', label: t('Class'), value: (r) => r.standard },
                { key: 'village', label: t('Village'), value: (r) => localName(r.village) },
                { key: 'group', label: t('Group'), value: (r) => localName(r.group) },
                { key: 'bal_panchayat', label: t('Bal Panchayat'), value: (r) => localName(r.bal_panchayat) },
                { key: 'phone', label: t('Mobile'), className: 'whitespace-nowrap', value: (r) => r.phone || r.household?.phone },
                { key: 'category', label: t('Category'), value: (r) => categoryLabel(r.household?.social_category) },
                { key: 'caste', label: t('Caste'), value: (r) => casteLabel(r) },
                { key: 'school_status', label: t('School'), value: (r) => r.school_status && t(humanize(r.school_status)) },
                { key: 'case', label: t('Cases'), value: (r) => r.case_summary?.open, render: (r) => <Badge tone="orange">{t('{n} open', { n: r.case_summary.open })}</Badge> },
                { key: 'anaemia', label: t('Anaemia'), value: (r) => r.health_summary?.anaemia_status, render: (r) => <StatusBadge value={r.health_summary.anaemia_status} /> },
                { key: 'last_participation_at', label: t('Last participation'), value: (r) => r.last_participation_at, render: (r) => fmtDate(r.last_participation_at) },
                { key: 'flags', label: '', value: (r) => r.flags?.needs_review || r.flags?.profile_incomplete, render: (r) => (r.flags?.needs_review ? <Badge tone="red">{t('Review')}</Badge> : r.flags?.profile_incomplete ? <Badge>{t('Incomplete')}</Badge> : null) },
              ])}
              rows={data?.items}
            />
            <Pagination page={page} pageSize={25} total={data?.total} onPage={setPage} />
          </>
        )}
      </Card>
      {creating && <Modal open={creating} title={t('Register a girl')} onClose={() => setCreating(false)} wide>
        <GirlForm onCancel={() => setCreating(false)} onSaved={(g) => nav(`/girls/${g.id}`)} />
      </Modal>}
    </div>
  )
}

