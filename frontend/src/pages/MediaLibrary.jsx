import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MediaGrid } from '../components/MediaGallery'
import { VillageSelect } from '../components/pickers'
import { Button, Card, ErrorBox, Field, Input, PageHeader, Pagination, Spinner } from '../components/ui'
import { fmtDateTime, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { bilingual, t } from '../lib/i18n'

const PAGE_SIZE = 24
const LINK = { event: (id) => `/events/${id}`, case: (id) => `/cases/${id}`, girl: (id) => `/girls/${id}` }

/** Every photo and file uploaded across the programme. Super Admin and Admin-1 only. */
export default function MediaLibrary() {
  const [f, setF] = useState({ village_id: '', start_date: '', end_date: '' })
  const [page, setPage] = useState(1)
  const { data, error, loading } = useFetch('/media/library', { ...f, page, page_size: PAGE_SIZE })
  const set = (k, v) => { setF((p) => ({ ...p, [k]: v })); setPage(1) }
  const filtered = f.village_id || f.start_date || f.end_date

  const meta = (m) => {
    const label = m.entity_label || t(humanize(m.entity_type))
    const to = LINK[m.entity_type]?.(m.entity_id)
    return (
      <>
        <div className="truncate font-medium text-gray-800">{bilingual(m.village_name, m.village_name_mr) || '—'}</div>
        <div className="truncate">{to ? <Link to={to} className="text-brand-700 hover:underline">{label}</Link> : label}</div>
        <div className="truncate text-gray-400">{fmtDateTime(m.uploaded_at)}{m.uploaded_by_name ? ` · ${m.uploaded_by_name}` : ''}</div>
      </>
    )
  }

  return (
    <div>
      <PageHeader title={t('Media library')} subtitle={t('All photos and files uploaded across villages')} />
      <Card>
        <div className="mb-4 grid gap-2 sm:grid-cols-4">
          <Field label={t('Village')}><VillageSelect value={f.village_id} onChange={(v) => set('village_id', v)} /></Field>
          <Field label={t('From')}><Input type="date" value={f.start_date} max={f.end_date || undefined} onChange={(e) => set('start_date', e.target.value)} /></Field>
          <Field label={t('To')}><Input type="date" value={f.end_date} min={f.start_date || undefined} onChange={(e) => set('end_date', e.target.value)} /></Field>
          <div className="flex items-end">
            <Button variant="secondary" disabled={!filtered} onClick={() => { setF({ village_id: '', start_date: '', end_date: '' }); setPage(1) }}>{t('Clear filters')}</Button>
          </div>
        </div>
        <ErrorBox message={error} />
        {data && <p className="mb-3 text-xs text-gray-500">{t('{n} files', { n: data.total })}</p>}
        {loading && !data ? <Spinner /> : (
          <MediaGrid media={data?.items} meta={meta} empty={filtered ? t('No media matches these filters.') : t('No media uploaded yet.')} />
        )}
        <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total} onPage={setPage} />
      </Card>
    </div>
  )
}
