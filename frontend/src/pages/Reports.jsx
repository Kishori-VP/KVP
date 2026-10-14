import { Download, FileText, Paperclip, Play, Plus, Share2, X } from 'lucide-react'
import { useState } from 'react'
import { PeriodPicker, TalukaSelect, VillageSelect } from '../components/pickers'
import { Badge, Button, Card, Checkbox, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from '../components/ui'
import api, { clean, download, errorMessage } from '../lib/api'
import { fmtDateTime, fmtNum, humanize, todayISO } from '../lib/format'
import { useAction, useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

const FORMATS = [
  { value: 'pdf', label: 'PDF' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'csv', label: 'CSV' },
  { value: 'docx', label: 'Word' },
]
const formatLabel = (f) => FORMATS.find((x) => x.value === f)?.label || f.toUpperCase()

/** Tick any number of file formats; several are downloaded together as one ZIP. */
function FormatPicker({ value, onChange, label = t('Formats') }) {
  const toggle = (f) => onChange(FORMATS.map((x) => x.value).filter((x) => (x === f ? !value.includes(f) : value.includes(x))))
  return (
    <Field label={label} group>
      <div className="flex flex-wrap gap-x-4 gap-y-1 py-1.5">
        {FORMATS.map((f) => <Checkbox key={f.value} label={f.label} checked={value.includes(f.value)} onChange={() => toggle(f.value)} />)}
      </div>
    </Field>
  )
}

const ATTACH_ACCEPT = '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

function uploadTemplateAttachment(templateId, file) {
  const fd = new FormData()
  fd.append('file', file)
  return api.post(`/reports/templates/${templateId}/attachments`, fd)
}

/** "Attach PDF / Word" button; calls onFiles with the chosen files. */
function AttachButton({ onFiles, busy, label = t('Attach PDF / Word') }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50">
      <Paperclip className="h-3.5 w-3.5" /> {busy ? t('Uploading…') : label}
      <input type="file" multiple accept={ATTACH_ACCEPT} className="sr-only" disabled={busy}
        onChange={(e) => { const files = [...e.target.files]; e.target.value = ''; if (files.length) onFiles(files) }} />
    </label>
  )
}

function downloadLabel(formats) {
  return formats.length > 1 ? t('Download {n} formats (ZIP)', { n: formats.length }) : t('Download {format}', { format: formatLabel(formats[0] || '') })
}

function ReportView({ report }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{report.title}</h2>
        <p className="text-sm text-gray-500">{report.subtitle} · {report.period.label}</p>
      </div>
      {report.summary.length > 0 && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {report.summary.map((s) => (
            <div key={s.label} className="rounded-lg border border-black/10 bg-white px-3 py-2">
              <div className="text-xs text-gray-500">{s.label}</div>
              <div className="text-lg font-semibold">{fmtNum(s.value)}</div>
            </div>
          ))}
        </div>
      )}
      {report.sections.map((sec) => (
        <Card key={sec.key || sec.title} title={sec.title} padded={false}>
          <Table rowKey={(r) => JSON.stringify(r)} columns={sec.columns.map((c) => ({
            key: c.key, label: c.label,
            render: (r) => { const v = r[c.key]; return Array.isArray(v) ? v.join(', ') : typeof v === 'string' && /^[a-z]+(_[a-z]+)+$/.test(v) ? <StatusBadge value={v} /> : fmtNum(v) },
          }))} rows={sec.totals ? [...sec.rows, { ...sec.totals, [sec.columns[0].key]: 'Total' }] : sec.rows} empty={t('No data for this period.')} />
        </Card>
      ))}
      {report.notes?.length > 0 && <ul className="list-disc pl-5 text-xs text-gray-500">{report.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    </div>
  )
}

function ShareModal({ open, onClose, onShare, initialFormats = ['pdf'] }) {
  const { data: users } = useFetch(open ? '/users' : null, { is_active: true, page_size: 200 })
  const [ids, setIds] = useState([])
  const [emails, setEmails] = useState('')
  const [formats, setFormats] = useState(initialFormats)
  const { busy, error, run } = useAction()
  const [result, setResult] = useState(null)
  const submit = () => run(async () => {
    setResult(await onShare({ recipient_user_ids: ids, recipient_emails: emails.split(',').map((e) => e.trim()).filter(Boolean), formats }))
  }).catch(() => {})
  return (
    <Modal open={open} title={t('Share report')} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Close')}</Button><Button busy={busy} disabled={(!ids.length && !emails.trim()) || !formats.length} onClick={submit}>{t('Generate & share')}</Button></>}>
      <ErrorBox message={error} />
      {result && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-900">Shared: {result.delivery.in_app} in-app · email {result.delivery.email}</p>}
      <Field label={t('Recipients (system users)')} group>
        <div className="max-h-40 space-y-1 overflow-y-auto">{(users?.items || []).map((u) => (
          <Checkbox key={u.id} label={`${u.name} (${humanize(u.role)})`} checked={ids.includes(u.id)} onChange={() => setIds(ids.includes(u.id) ? ids.filter((x) => x !== u.id) : [...ids, u.id])} />
        ))}</div>
      </Field>
      <Field label={t('External emails')} hint={t('Must be on the allow-list (Configuration → Report sharing)')}><Input placeholder={t('donor@example.org, …')} value={emails} onChange={(e) => setEmails(e.target.value)} /></Field>
      <FormatPicker value={formats} onChange={setFormats} />
    </Modal>
  )
}

function RunReport() {
  const { data: types } = useFetch('/reports/types')
  const [type, setType] = useState('programme_summary')
  const [period, setPeriod] = useState({ period: 'monthly', reference_date: todayISO() })
  const [scope, setScope] = useState({ taluka_id: '', village_id: '' })
  const [report, setReport] = useState(null)
  const [sharing, setSharing] = useState(false)
  const [formats, setFormats] = useState(['pdf'])
  const [downloading, setDownloading] = useState(false)
  const { busy, error, run } = useAction()
  const params = clean({ ...period, ...scope })
  const exportFiles = () => run(async () => {
    setDownloading(true)
    try {
      await download(`/reports/${type}`, { ...params, formats: formats.join(',') })
    } finally {
      setDownloading(false)
    }
  }).catch(() => {})
  const go = () => run(async () => setReport((await api.get(`/reports/${type}`, { params })).data)).catch(() => {})
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end gap-2">
          <Field label={t('Report')}><Select options={Object.entries(types?.report_types || {}).map(([value, label]) => ({ value, label }))} value={type} onChange={(e) => { setType(e.target.value); setReport(null) }} /></Field>
          <PeriodPicker value={period} onChange={setPeriod} />
          <Field label={t('Taluka')}><TalukaSelect value={scope.taluka_id} onChange={(v) => setScope({ taluka_id: v, village_id: '' })} /></Field>
          <Field label={t('Village')}><VillageSelect value={scope.village_id} talukaId={scope.taluka_id} onChange={(v) => setScope({ ...scope, village_id: v })} /></Field>
          <Button icon={Play} busy={busy && !downloading} onClick={go}>{t('Run')}</Button>
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-gray-100 pt-3">
          <FormatPicker value={formats} onChange={setFormats} label={t('Download formats')} />
          <Button variant="secondary" icon={Download} busy={downloading} disabled={!formats.length} onClick={exportFiles}>{downloadLabel(formats)}</Button>
          <Button variant="secondary" icon={Share2} onClick={() => setSharing(true)}>{t('Share')}</Button>
        </div>
      </Card>
      <ErrorBox message={error} />
      {report && <ReportView report={report} />}
      <ShareModal key={String(sharing)} open={sharing} onClose={() => setSharing(false)} initialFormats={formats.length ? formats : ['pdf']}
        onShare={async (b) => (await api.post(`/reports/${type}/share`, { ...params, ...b })).data} />
    </div>
  )
}

function TemplateBuilder({ onClose, onSaved, types }) {
  const [f, setF] = useState({ name: '', report_type: 'village_wise', default_period: 'monthly', include_summary: true, append_default_notes: true, default_formats: ['pdf'], sel: {}, summary_labels: [] })
  const { data: structure } = useFetch(`/reports/types/${f.report_type}/structure`)
  const [files, setFiles] = useState([])
  const { busy, error, run } = useAction()
  const toggleSection = (key, cols) => setF({ ...f, sel: { ...f.sel, [key]: f.sel[key] ? undefined : { columns: cols.map((c) => c.key), title: '' } } })
  const toggleCol = (key, col) => {
    const cur = f.sel[key].columns
    setF({ ...f, sel: { ...f.sel, [key]: { ...f.sel[key], columns: cur.includes(col) ? cur.filter((c) => c !== col) : [...cur, col] } } })
  }
  const save = () => run(async () => {
    const sections = Object.entries(f.sel).filter(([, v]) => v).map(([key, v]) => ({ key, title: v.title || null, columns: v.columns }))
    const created = await api.post('/reports/templates', {
      name: f.name, report_type: f.report_type, default_period: f.default_period, description: f.description || null,
      taluka_id: f.taluka_id || null, village_id: f.village_id || null, title: f.title || null, subtitle_note: f.subtitle_note || null,
      include_summary: f.include_summary, summary_labels: f.summary_labels.length ? f.summary_labels : null,
      sections: sections.length ? sections : null, notes: f.notes ? f.notes.split('\n').filter(Boolean) : null,
      append_default_notes: f.append_default_notes, default_formats: f.default_formats,
    })
    const failed = []
    for (const file of files) {
      try {
        await uploadTemplateAttachment(created.data.id, file)
      } catch (e) {
        failed.push(`${file.name}: ${errorMessage(e)}`)
      }
    }
    if (failed.length) alert(`${t('The template was saved, but some attachments failed. You can attach them again from the template list.')}\n${failed.join('\n')}`)
    onSaved()
  }).catch(() => {})
  return (
    <Modal open title={t('New report template')} onClose={onClose} wide
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={f.name.length < 3 || !f.default_formats.length} onClick={save}>{t('Save template')}</Button></>}>
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Template name *')}><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('Report type')}><Select options={Object.entries(types || {}).map(([value, label]) => ({ value, label }))} value={f.report_type} onChange={(e) => setF({ ...f, report_type: e.target.value, sel: {}, summary_labels: [] })} /></Field>
        <Field label={t('Default period')}><Select options={['daily', 'weekly', 'monthly', 'quarterly', 'yearly']} value={f.default_period} onChange={(e) => setF({ ...f, default_period: e.target.value })} /></Field>
        <Field label={t('Custom title')}><Input value={f.title || ''} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label={t('Taluka scope')}><TalukaSelect value={f.taluka_id} onChange={(v) => setF({ ...f, taluka_id: v, village_id: '' })} /></Field>
        <Field label={t('Village scope')}><VillageSelect value={f.village_id} talukaId={f.taluka_id} onChange={(v) => setF({ ...f, village_id: v })} /></Field>
        <Field label={t('Subtitle note')} className="sm:col-span-2"><Input placeholder={t('e.g. Prepared for XYZ Foundation')} value={f.subtitle_note || ''} onChange={(e) => setF({ ...f, subtitle_note: e.target.value })} /></Field>
      </div>
      {!structure ? <Spinner /> : (
        <>
          <Checkbox label={t('Include summary indicators')} checked={f.include_summary} onChange={(e) => setF({ ...f, include_summary: e.target.checked })} />
          {f.include_summary && structure.summary_labels.length > 0 && (
            <Field label={t('Summary items (none ticked = all)')} group>
              <div className="flex flex-wrap gap-3">{structure.summary_labels.map((l) => (
                <Checkbox key={l} label={l} checked={f.summary_labels.includes(l)} onChange={() => setF({ ...f, summary_labels: f.summary_labels.includes(l) ? f.summary_labels.filter((x) => x !== l) : [...f.summary_labels, l] })} />
              ))}</div>
            </Field>
          )}
          <Field label={t('Sections & columns (none ticked = all)')} group>
            <div className="space-y-3">{structure.sections.map((s) => (
              <div key={s.key} className="rounded-lg border border-gray-200 p-3">
                <Checkbox label={<b>{s.title}</b>} checked={Boolean(f.sel[s.key])} onChange={() => toggleSection(s.key, s.columns)} />
                {f.sel[s.key] && (
                  <div className="mt-2 space-y-2 pl-6">
                    <Input placeholder={t('Rename section (optional)')} value={f.sel[s.key].title} onChange={(e) => setF({ ...f, sel: { ...f.sel, [s.key]: { ...f.sel[s.key], title: e.target.value } } })} />
                    <div className="flex flex-wrap gap-3">{s.columns.map((c) => <Checkbox key={c.key} label={c.label} checked={f.sel[s.key].columns.includes(c.key)} onChange={() => toggleCol(s.key, c.key)} />)}</div>
                  </div>
                )}
              </div>
            ))}</div>
          </Field>
        </>
      )}
      <Field label={t('Notes (one per line)')}><Textarea value={f.notes || ''} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      <Checkbox label={t("Also include the report's standard notes")} checked={f.append_default_notes} onChange={(e) => setF({ ...f, append_default_notes: e.target.checked })} />
      <FormatPicker label={t('Default download formats')} value={f.default_formats} onChange={(v) => setF({ ...f, default_formats: v })} />
      <Field label={t('Attachments (PDF / Word)')} hint={t('Included with every download, share and scheduled email of this template — e.g. a cover letter or annexure.')} group>
        <div className="space-y-1.5">
          {files.map((file, i) => (
            <div key={`${file.name}-${i}`} className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4 shrink-0 text-gray-500" /> <span className="truncate">{file.name}</span>
              <button type="button" className="text-gray-400 hover:text-red-700" aria-label={t('Remove')} onClick={() => setFiles(files.filter((_, j) => j !== i))}><X className="h-4 w-4" /></button>
            </div>
          ))}
          <AttachButton onFiles={(more) => setFiles([...files, ...more].slice(0, 5))} />
        </div>
      </Field>
    </Modal>
  )
}

function Templates() {
  const { data: types } = useFetch('/reports/types')
  const { data, error, reload } = useFetch('/reports/templates')
  const [building, setBuilding] = useState(false)
  const [preview, setPreview] = useState(null)
  const [sharing, setSharing] = useState(null)
  const { busy, error: actErr, run } = useAction()
  const show = (tpl) => run(async () => setPreview((await api.get(`/reports/templates/${tpl.id}/run`)).data)).catch(() => {})
  const remove = (tpl) => run(async () => { await api.delete(`/reports/templates/${tpl.id}`); reload() }).catch(() => {})
  const [attaching, setAttaching] = useState(null)
  const attach = (tpl, files) => run(async () => {
    setAttaching(tpl.id)
    try {
      for (const file of files) await uploadTemplateAttachment(tpl.id, file)
    } finally {
      setAttaching(null)
      reload()
    }
  }).catch(() => {})
  const detach = (tpl, a) => run(async () => { await api.delete(`/reports/templates/${tpl.id}/attachments/${a.id}`); reload() }).catch(() => {})
  return (
    <div className="space-y-4">
      <Card title={t('Report templates')} actions={<Button size="sm" icon={Plus} onClick={() => setBuilding(true)}>{t('New template')}</Button>}>
        <ErrorBox message={error || actErr} />
        <Table columns={[
          { key: 'name', label: t('Template'), className: 'font-medium' },
          { key: 'report_type', label: t('Based on'), render: (tpl) => types?.report_types?.[tpl.report_type] || tpl.report_type },
          { key: 'default_period', label: t('Period'), render: (tpl) => humanize(tpl.default_period) },
          { key: 'sections', label: t('Sections'), render: (tpl) => (tpl.sections ? tpl.sections.length : t('All')) },
          { key: 'default_formats', label: t('Formats'), render: (tpl) => (tpl.default_formats || ['pdf']).map(formatLabel).join(', ') },
          { key: 'attachments', label: t('Attachments'), render: (tpl) => (
            <div className="space-y-1">
              {(tpl.attachments || []).map((a) => (
                <div key={a.id} className="flex items-center gap-1.5 text-xs">
                  <button type="button" className="inline-flex items-center gap-1 text-brand-700 hover:underline" onClick={() => run(() => download(`/reports/templates/${tpl.id}/attachments/${a.id}`)).catch(() => {})}>
                    <FileText className="h-3.5 w-3.5" /> {a.original_name}
                  </button>
                  <button type="button" className="text-gray-400 hover:text-red-700" aria-label={t('Remove')} onClick={() => detach(tpl, a)}><X className="h-3.5 w-3.5" /></button>
                </div>
              ))}
              {(tpl.attachments || []).length < 5 && <AttachButton busy={attaching === tpl.id} label={t('Attach')} onFiles={(files) => attach(tpl, files)} />}
            </div>) },
          { key: 'actions', label: '', render: (tpl) => (
            <span className="flex flex-wrap gap-1">
              <Button size="sm" variant="secondary" busy={busy} onClick={() => show(tpl)}>{t('Preview')}</Button>
              <Button size="sm" variant="secondary" icon={Download} onClick={() => run(() => download(`/reports/templates/${tpl.id}/run`, { formats: (tpl.default_formats || ['pdf']).join(',') })).catch(() => {})}>{tpl.attachments?.length ? t('Download with attachments (ZIP)') : downloadLabel(tpl.default_formats || ['pdf'])}</Button>
              <Button size="sm" variant="secondary" onClick={() => setSharing(tpl)}>{t('Share')}</Button>
              <Button size="sm" variant="ghost" onClick={() => remove(tpl)}>{t('Remove')}</Button>
            </span>) },
        ]} rows={data} empty={t('No templates yet. A template saves a report type, scope, chosen sections/columns and a custom title.')} />
      </Card>
      {preview && <ReportView report={preview} />}
      {building && <TemplateBuilder types={types?.report_types} onClose={() => setBuilding(false)} onSaved={() => { setBuilding(false); reload() }} />}
      <ShareModal key={sharing?.id || 'none'} open={Boolean(sharing)} onClose={() => setSharing(null)} initialFormats={sharing?.default_formats || ['pdf']}
        onShare={async (b) => (await api.post(`/reports/templates/${sharing.id}/share`, b)).data} />
    </div>
  )
}

function Schedules() {
  const { data: types } = useFetch('/reports/types')
  const { data: templates } = useFetch('/reports/templates')
  const { data: users } = useFetch('/users', { is_active: true, page_size: 200 })
  const { data, reload } = useFetch('/reports/schedules')
  const [f, setF] = useState(null)
  const { busy, error, run } = useAction()
  const save = () => run(async () => {
    await api.post('/reports/schedules', {
      name: f.name, frequency: f.frequency, run_time: f.run_time, formats: f.formats,
      ...(f.source === 'template' ? { template_id: f.template_id } : { report_type: f.report_type }),
      recipient_user_ids: f.recipient_user_ids, recipient_emails: f.emails ? f.emails.split(',').map((e) => e.trim()).filter(Boolean) : [],
    })
    setF(null)
    reload()
  }).catch(() => {})
  const toggle = (s) => run(async () => { await api.patch(`/reports/schedules/${s.id}`, { is_active: !s.is_active }); reload() }).catch(() => {})
  const runNow = (s) => run(async () => { await api.post(`/reports/schedules/${s.id}/run-now`); reload() }).catch(() => {})
  return (
    <Card title={t('Scheduled reports')} actions={<Button size="sm" icon={Plus} onClick={() => setF({ source: 'type', report_type: 'programme_summary', frequency: 'monthly', run_time: '07:00', formats: ['pdf'], recipient_user_ids: [] })}>{t('New schedule')}</Button>}>
      <ErrorBox message={error} />
      <Table columns={[
        { key: 'name', label: t('Schedule'), className: 'font-medium' },
        { key: 'report_type', label: t('Report'), render: (s) => (s.template_id ? <Badge tone="brand">{t('Template')}</Badge> : types?.report_types?.[s.report_type]) },
        { key: 'formats', label: t('Formats'), render: (s) => (s.formats || []).map(formatLabel).join(', ') },
        { key: 'frequency', label: t('Every'), render: (s) => t('{freq} at {time}', { freq: humanize(s.frequency), time: s.run_time }) },
        { key: 'next_run_at', label: t('Next run'), render: (s) => fmtDateTime(s.next_run_at) },
        { key: 'last', label: t('Last run'), render: (s) => (s.last_run_at ? <span>{fmtDateTime(s.last_run_at)} <StatusBadge value={s.last_result?.status === 'ok' ? 'completed' : 'failed'} /></span> : '—') },
        { key: 'is_active', label: '', render: (s) => (
          <span className="flex gap-1">
            <Button size="sm" variant="secondary" busy={busy} onClick={() => runNow(s)}>{t('Run now')}</Button>
            <Button size="sm" variant="ghost" onClick={() => toggle(s)}>{s.is_active ? t('Pause') : t('Resume')}</Button>
          </span>) },
      ]} rows={data} empty={t('No schedules. Reports are generated for the period that just ended and shared with the recipients.')} />
      {f && (
        <Modal open title={t('New report schedule')} onClose={() => setF(null)}
          footer={<><Button variant="secondary" onClick={() => setF(null)}>{t('Cancel')}</Button><Button busy={busy} disabled={!f.name || (!f.recipient_user_ids.length && !f.emails) || !f.formats.length} onClick={save}>{t('Create')}</Button></>}>
          <ErrorBox message={error} />
          <Field label={t('Name *')}><Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label={t('Source')}><Select options={[{ value: 'type', label: t('Standard report') }, { value: 'template', label: t('Saved template') }]} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} /></Field>
          {f.source === 'type'
            ? <Field label={t('Report')}><Select options={Object.entries(types?.report_types || {}).map(([value, label]) => ({ value, label }))} value={f.report_type} onChange={(e) => setF({ ...f, report_type: e.target.value })} /></Field>
            : <Field label={t('Template')}><Select options={(templates || []).map((tpl) => ({ value: tpl.id, label: tpl.name }))} placeholder={t('Select…')} value={f.template_id || ''} onChange={(e) => setF({ ...f, template_id: e.target.value })} /></Field>}
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('Frequency')}><Select options={['daily', 'weekly', 'monthly', 'quarterly', 'yearly']} value={f.frequency} onChange={(e) => setF({ ...f, frequency: e.target.value })} /></Field>
            <Field label={t('Run time (IST)')}><Input type="time" value={f.run_time} onChange={(e) => setF({ ...f, run_time: e.target.value })} /></Field>
          </div>
          <FormatPicker value={f.formats} onChange={(v) => setF({ ...f, formats: v })} />
          <Field label={t('Recipients')} group>
            <div className="max-h-32 space-y-1 overflow-y-auto">{(users?.items || []).map((u) => (
              <Checkbox key={u.id} label={u.name} checked={f.recipient_user_ids.includes(u.id)}
                onChange={() => setF({ ...f, recipient_user_ids: f.recipient_user_ids.includes(u.id) ? f.recipient_user_ids.filter((x) => x !== u.id) : [...f.recipient_user_ids, u.id] })} />
            ))}</div>
          </Field>
          <Field label={t('External emails (allow-listed)')}><Input value={f.emails || ''} onChange={(e) => setF({ ...f, emails: e.target.value })} /></Field>
        </Modal>
      )}
    </Card>
  )
}

function Generated() {
  const { data } = useFetch('/reports/generated', { page_size: 50 })
  return (
    <Card title={t('Generated reports')}>
      {!data ? <Spinner /> : (
        <Table columns={[
          { key: 'created_at', label: t('Generated'), render: (r) => fmtDateTime(r.created_at) },
          { key: 'title', label: t('Report'), className: 'font-medium' },
          { key: 'period', label: t('Period'), render: (r) => r.period?.label },
          { key: 'delivery', label: t('Delivery'), render: (r) => t('{a} in-app · email {b}', { a: r.delivery.in_app, b: r.delivery.email }) },
          { key: 'files', label: t('Download'), render: (r) => (
            <span className="flex flex-wrap gap-1">{r.files.map((f) => (
              <Button key={`${f.format}-${f.name || ''}`} size="sm" variant="secondary" icon={f.format === 'attachment' ? Paperclip : undefined}
                onClick={() => download(`/reports/generated/${r.id}/download`, clean({ format: f.format, name: f.name }))}>
                {f.format === 'attachment' ? f.name : formatLabel(f.format)}
              </Button>
            ))}</span>) },
        ]} rows={data.items} empty={t('No reports generated yet.')} />
      )}
    </Card>
  )
}

export default function Reports() {
  const [tab, setTab] = useState('run')
  return (
    <div>
      <PageHeader title={t('Reports & analytics')} subtitle={t('Daily to yearly · village, taluka, volunteer and activity reports · PDF, Excel, CSV & Word')} />
      <Tabs tabs={[{ value: 'run', label: t('Run a report') }, { value: 'templates', label: t('Templates') }, { value: 'schedules', label: t('Schedules') }, { value: 'generated', label: t('Generated') }]} value={tab} onChange={setTab} />
      {tab === 'run' && <RunReport />}
      {tab === 'templates' && <Templates />}
      {tab === 'schedules' && <Schedules />}
      {tab === 'generated' && <Generated />}
    </div>
  )
}
