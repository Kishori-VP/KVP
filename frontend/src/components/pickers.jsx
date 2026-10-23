import { bilingual, localName, t } from '../lib/i18n'
import { useFetch, useLookups, useTalukas, useVillages, useVolunteers } from '../lib/hooks'
import { Field, Input, Select } from './ui'

export function VillageSelect({ value, onChange, placeholder = t('All villages'), talukaId, ...props }) {
  const villages = useVillages()
  const opts = villages
    .filter((v) => !talukaId || v.taluka_id === talukaId)
    .map((v) => ({ value: v.id, label: bilingual(v.name, v.name_mr) }))
  return <Select options={opts} placeholder={placeholder} value={value || ''} onChange={(e) => onChange(e.target.value)} {...props} />
}

/** Pick any number of villages (a volunteer can work in several). Value: array of village ids. */
export function VillageMultiSelect({ value = [], onChange, villages: only }) {
  const all = useVillages()
  const villages = only ? all.filter((v) => only.includes(v.id)) : all
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  if (!villages.length) return <p className="text-xs text-gray-500">{t('No villages available.')}</p>
  return (
    <div className="flex max-h-48 flex-wrap gap-2 overflow-y-auto">
      {villages.map((v) => (
        <label
          key={v.id}
          className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${value.includes(v.id) ? 'border-brand-500 bg-brand-50 text-brand-800' : 'border-gray-300 text-gray-700'}`}
        >
          <input type="checkbox" className="sr-only" checked={value.includes(v.id)} onChange={() => toggle(v.id)} />
          {bilingual(v.name, v.name_mr)}
        </label>
      ))}
    </div>
  )
}

/** Ids of the villages a volunteer (or user) works in. */
export function villageIdsOf(person) {
  if (!person) return []
  return person.village_ids?.length ? person.village_ids : person.village_id ? [person.village_id] : []
}

export function TalukaSelect({ value, onChange, placeholder = t('All talukas') }) {
  const talukas = useTalukas()
  return (
    <Select
      options={talukas.map((t) => ({ value: t.id, label: bilingual(t.name, t.name_mr) }))}
      placeholder={placeholder}
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export function VolunteerSelect({ value, onChange, villageId, placeholder = t('All volunteers') }) {
  const vols = useVolunteers()
  const opts = (Array.isArray(vols) ? vols : [])
    .filter((v) => !villageId || villageIdsOf(v).includes(villageId))
    .map((v) => ({ value: v.id, label: v.village_name ? `${bilingual(v.name, v.name_mr)} (${bilingual(v.village_name, v.village_name_mr)})` : bilingual(v.name, v.name_mr) }))
  return <Select options={opts} placeholder={placeholder} value={value || ''} onChange={(e) => onChange(e.target.value)} />
}

export function GroupSelect({ value, onChange, villageId, placeholder = t('All groups'), groupType = 'kishori' }) {
  const { data } = useFetch(villageId ? '/groups' : null, { village_id: villageId, group_type: groupType, page_size: 200 })
  return (
    <Select
      options={(data?.items || []).map((g) => ({ value: g.id, label: localName(g) }))}
      placeholder={villageId ? placeholder : t('Pick a village first')}
      value={value || ''}
      disabled={!villageId}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

export function LookupSelect({ type, value, onChange, placeholder = t('Select…'), ...props }) {
  const items = useLookups(type)
  return (
    <Select
      options={items.map((l) => ({ value: l.code, label: bilingual(l.label, l.label_mr) }))}
      placeholder={placeholder}
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
      {...props}
    />
  )
}

/** Groups of one village (villageId) or of several villages (villageIds). */
export function GroupMultiSelect({ villageId, villageIds, value = [], onChange }) {
  const ids = villageIds || (villageId ? [villageId] : [])
  const villages = useVillages()
  const { data } = useFetch(ids.length ? '/groups' : null, ids.length === 1 ? { village_id: ids[0], page_size: 500 } : { page_size: 500 })
  const groups = (data?.items || []).filter((g) => [g.village_id, ...(g.member_village_ids || [])].some((id) => ids.includes(id)))
  const villageName = (id) => villages.find((v) => v.id === id)?.name
  if (!ids.length) return <p className="text-xs text-gray-500">{t('Pick a village to choose groups.')}</p>
  if (!groups.length) return <p className="text-xs text-gray-500">{ids.length > 1 ? t('These villages have no groups.') : t('This village has no groups.')}</p>
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  return (
    <div className="flex flex-wrap gap-2">
      {groups.map((g) => (
        <label
          key={g.id}
          className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${value.includes(g.id) ? 'border-brand-500 bg-brand-50 text-brand-800' : 'border-gray-300 text-gray-700'}`}
        >
          <input type="checkbox" className="sr-only" checked={value.includes(g.id)} onChange={() => toggle(g.id)} />
          {localName(g)} {g.group_type === 'bal_panchayat' && <span className="text-gray-400">(BP)</span>}
          {ids.length > 1 && <span className="text-gray-400"> · {villageName(g.village_id)}</span>}
        </label>
      ))}
    </div>
  )
}

export const PERIODS = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly', 'custom']

/** value: {period, reference_date, start_date, end_date} */
export function PeriodPicker({ value, onChange, allowCustom = true }) {
  const set = (k, v) => onChange({ ...value, [k]: v })
  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field label={t('Period')}>
        <Select options={allowCustom ? PERIODS : PERIODS.slice(0, 5)} value={value.period} onChange={(e) => set('period', e.target.value)} />
      </Field>
      {value.period === 'custom' ? (
        <>
          <Field label={t('From')}>
            <Input type="date" value={value.start_date || ''} onChange={(e) => set('start_date', e.target.value)} />
          </Field>
          <Field label={t('To')}>
            <Input type="date" value={value.end_date || ''} onChange={(e) => set('end_date', e.target.value)} />
          </Field>
        </>
      ) : (
        <Field label={t('Containing date')}>
          <Input type="date" value={value.reference_date || ''} onChange={(e) => set('reference_date', e.target.value)} />
        </Field>
      )}
    </div>
  )
}
