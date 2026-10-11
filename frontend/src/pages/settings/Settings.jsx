import { Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge, Button, Card, Checkbox, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, Table, Tabs, Textarea } from '../../components/ui'
import api, { errorMessage } from '../../lib/api'
import { fmtDateTime, humanize } from '../../lib/format'
import { invalidateRefData, useAction, useFetch } from '../../lib/hooks'
import { t } from '../../lib/i18n'

function Lookups() {
  const { data: meta } = useFetch('/config/lookup-types')
  const [type, setType] = useState('event_type')
  const { data, reload } = useFetch('/config/lookups', { type, include_inactive: true })
  const [edit, setEdit] = useState(null)
  const { busy, error, run, setError } = useAction()
  const save = () => run(async () => {
    let attributes
    try { attributes = edit.attributes_text ? JSON.parse(edit.attributes_text) : {} } catch { setError(t('Attributes must be valid JSON')); throw new Error('json') }
    const body = { label: edit.label, label_mr: edit.label_mr || null, description: edit.description || null, order: Number(edit.order || 0), is_active: edit.is_active, attributes }
    if (edit.id) await api.patch(`/config/lookups/${edit.id}`, body)
    else await api.post('/config/lookups', { ...body, type, code: edit.code })
    invalidateRefData()
    setEdit(null)
    reload()
  }).catch(() => {})
  const hint = { target_type: `{"metric": "home_visits"} — ${t('metrics')}: ${Object.keys(meta?.target_metrics || {}).join(', ')}`, health_field: '{"data_type": "number|text|boolean|select", "options": [...], "required": false}', event_type: `{"is_meeting": true} ${t('counts as a group meeting')}`, contact_category: `{"mandatory": true} ${t('for the four key contacts')}` }[type]
  return (
    <Card title={t('Dropdown lists')} actions={<>
      <Select options={Object.entries(meta?.types || {}).map(([value, label]) => ({ value, label: `${humanize(value)} — ${label}` }))} value={type} onChange={(e) => setType(e.target.value)} />
      <Button size="sm" icon={Plus} onClick={() => setEdit({ is_active: true, order: (data?.length || 0) + 1, attributes_text: '{}' })}>{t('Add')}</Button>
    </>}>
      {!data ? <Spinner /> : (
        <Table onRowClick={(r) => setEdit({ ...r, attributes_text: JSON.stringify(r.attributes || {}) })} columns={[
          { key: 'code', label: t('Code'), className: 'font-mono text-xs' }, { key: 'label', label: t('Label') }, { key: 'label_mr', label: 'मराठी' },
          { key: 'attributes', label: t('Attributes'), render: (r) => <span className="font-mono text-xs">{JSON.stringify(r.attributes || {})}</span> },
          { key: 'is_active', label: '', render: (r) => (r.is_active ? null : <Badge>{t('Inactive')}</Badge>) },
        ]} rows={data} />
      )}
      {edit && (
        <Modal open title={edit.id ? t('Edit {code}', { code: edit.code }) : t('Add {type}', { type: humanize(type) })} onClose={() => setEdit(null)}
          footer={<><Button variant="secondary" onClick={() => setEdit(null)}>{t('Cancel')}</Button><Button busy={busy} disabled={!edit.label || (!edit.id && !edit.code)} onClick={save}>{t('Save')}</Button></>}>
          <ErrorBox message={error} />
          {!edit.id && <Field label={t('Code (lowercase_with_underscores) *')}><Input value={edit.code || ''} onChange={(e) => setEdit({ ...edit, code: e.target.value })} /></Field>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('Label *')}><Input value={edit.label || ''} onChange={(e) => setEdit({ ...edit, label: e.target.value })} /></Field>
            <Field label={t('Marathi label')}><Input value={edit.label_mr || ''} onChange={(e) => setEdit({ ...edit, label_mr: e.target.value })} /></Field>
            <Field label={t('Order')}><Input type="number" value={edit.order} onChange={(e) => setEdit({ ...edit, order: e.target.value })} /></Field>
          </div>
          <Field label={t('Attributes (JSON)')} hint={hint}><Textarea value={edit.attributes_text} onChange={(e) => setEdit({ ...edit, attributes_text: e.target.value })} /></Field>
          <Checkbox label={t('Active')} checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
        </Modal>
      )}
    </Card>
  )
}

const SETTING_HELP = {
  target_thresholds: 'When a target counts as On Track / low performance, and when deadline reminders start',
  escalation_rules: 'Case due dates by severity, stale-case window and escalation reminders',
  village_status: 'Days since last field activity for On Track / Delayed / No Recent Activity',
  duplicate_matching: 'Fields and thresholds for beneficiary duplicate detection',
  girl_id: 'Girl ID format for new registrations',
  anaemia_thresholds: 'Haemoglobin cut-offs (g/dL)',
  reporting: 'Expected daily reports and working days (Monday = 0)',
  validation_rules: 'Mandatory fields and validation rules per form',
  messaging: 'SMS reminder text for event participants ({title} {date} {time} {place})',
  report_sharing: 'External email addresses allowed to receive reports',
}

function SettingEditor({ k, value, onSaved }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2))
  const [msg, setMsg] = useState(null)
  const { busy, error, run, setError } = useAction()
  useEffect(() => setText(JSON.stringify(value, null, 2)), [value])
  const save = () => run(async () => {
    let parsed
    try { parsed = JSON.parse(text) } catch { setError(t('Not valid JSON')); throw new Error('json') }
    const r = await api.put(`/config/settings/${k}`, parsed)
    setMsg(t('Saved'))
    onSaved(k, r.data)
  }).catch(() => {})
  return (
    <Card title={humanize(k)} actions={<Button size="sm" busy={busy} onClick={save}>{t('Save')}</Button>}>
      <p className="mb-2 text-xs text-gray-500">{SETTING_HELP[k] && t(SETTING_HELP[k])}</p>
      <ErrorBox message={error} />
      {msg && <p className="mb-2 text-xs text-green-700">{msg}</p>}
      <textarea className="h-48 w-full rounded-lg border border-gray-300 p-2 font-mono text-xs" value={text} onChange={(e) => { setText(e.target.value); setMsg(null) }} />
    </Card>
  )
}

function Rules() {
  const { data, setData } = useFetch('/config/settings')
  if (!data) return <Spinner />
  const keys = Object.keys(data).filter((k) => k !== 'permissions')
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {keys.map((k) => <SettingEditor key={k} k={k} value={data[k]} onSaved={(key, v) => setData({ ...data, [key]: v })} />)}
    </div>
  )
}

function Permissions() {
  const { data, reload } = useFetch('/config/permissions')
  const [matrix, setMatrix] = useState(null)
  const { busy, error, run } = useAction()
  useEffect(() => { if (data) setMatrix(data.matrix.volunteer) }, [data])
  if (!data || !matrix) return <Spinner />
  const toggle = (r, a) => setMatrix({ ...matrix, [r]: matrix[r].includes(a) ? matrix[r].filter((x) => x !== a) : [...matrix[r], a] })
  const save = () => run(async () => {
    await api.put('/config/settings/permissions', { volunteer: Object.fromEntries(Object.entries(matrix).filter(([r]) => !data.stakeholder_only.includes(r))) })
    reload()
  }).catch(() => {})
  return (
    <Card title={t('Permission matrix')} actions={<Button size="sm" busy={busy} onClick={save}>{t('Save volunteer permissions')}</Button>}>
      <ErrorBox message={error} />
      <p className="mb-3 text-sm text-gray-600">{data.notes}</p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead><tr className="border-b text-left text-xs uppercase text-gray-500"><th className="px-2 py-2">{t('Resource')}</th><th className="px-2">{t('Stakeholder')}</th>{data.actions.map((a) => <th key={a} className="px-2 text-center">Volunteer: {a}</th>)}</tr></thead>
          <tbody>
            {data.resources.map((r) => {
              const locked = data.stakeholder_only.includes(r)
              return (
                <tr key={r} className="border-b border-gray-100">
                  <td className="px-2 py-1.5 font-medium">{humanize(r)}</td>
                  <td className="px-2 text-xs text-green-700">{t('All')}</td>
                  {data.actions.map((a) => (
                    <td key={a} className="px-2 text-center">
                      {locked ? <span className="text-xs text-gray-300">—</span> : <input type="checkbox" className="h-4 w-4" checked={matrix[r]?.includes(a) || false} onChange={() => toggle(r, a)} />}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Providers() {
  const { data, error, reload } = useFetch('/config/providers')
  const [edit, setEdit] = useState(null)
  const { busy, error: actErr, run, setError } = useAction()
  const save = () => run(async () => {
    let config
    try { config = edit.config_text ? JSON.parse(edit.config_text) : {} } catch { setError(t('Config must be valid JSON')); throw new Error('json') }
    const credentials = Object.fromEntries(edit.creds.filter((c) => c.key && c.value).map((c) => [c.key, c.value]))
    await api.put('/config/providers', { provider_type: edit.provider_type, provider_name: edit.provider_name, is_active: edit.is_active, is_default: edit.is_default, config, credentials: Object.keys(credentials).length ? credentials : null })
    setEdit(null)
    reload()
  }).catch(() => {})
  const remove = async (p) => { try { await api.delete(`/config/providers/${p.id}`); reload() } catch (e) { alert(errorMessage(e)) } }
  return (
    <Card title={t('AI / OCR / voice / SMS providers')} actions={<Button size="sm" icon={Plus} onClick={() => setEdit({ provider_type: 'speech_to_text', provider_name: '', is_active: false, is_default: false, config_text: '{}', creds: [{ key: 'api_key', value: '' }] })}>{t('Add provider')}</Button>}>
      <ErrorBox message={error} />
      <p className="mb-3 text-xs text-gray-500">{t('Credentials are encrypted on the server and are never shown again — only masked. SMS providers:')} <b>console</b> {t('(log only)')}, <b>twilio</b>, <b>fast2sms</b>.</p>
      <Table columns={[
        { key: 'provider_type', label: t('Type'), render: (p) => humanize(p.provider_type) },
        { key: 'provider_name', label: t('Provider'), className: 'font-medium' },
        { key: 'state', label: t('Status'), render: (p) => <span className="flex gap-1">{p.is_active ? <Badge tone="green">{t('Active')}</Badge> : <Badge>{t('Inactive')}</Badge>}{p.is_default && <Badge tone="brand">{t('Default')}</Badge>}</span> },
        { key: 'credentials_masked', label: t('Credentials'), render: (p) => Object.entries(p.credentials_masked || {}).map(([k, v]) => `${k}: ${v}`).join(', ') || '—' },
        { key: 'updated_at', label: t('Updated'), render: (p) => fmtDateTime(p.updated_at) },
        { key: 'x', label: '', render: (p) => <span className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => setEdit({ ...p, config_text: JSON.stringify(p.config || {}), creds: Object.keys(p.credentials_masked || {}).map((k) => ({ key: k, value: '' })) })}>{t('Edit')}</Button>
          <Button size="sm" variant="ghost" onClick={() => remove(p)}>{t('Delete')}</Button></span> },
      ]} rows={data} empty={t('No providers configured.')} />
      {edit && (
        <Modal open title={t('Provider configuration')} onClose={() => setEdit(null)}
          footer={<><Button variant="secondary" onClick={() => setEdit(null)}>{t('Cancel')}</Button><Button busy={busy} disabled={!edit.provider_name} onClick={save}>{t('Save')}</Button></>}>
          <ErrorBox message={actErr} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('Type')}><Select options={['ocr', 'speech_to_text', 'llm', 'translation', 'sms', 'email', 'maps', 'push']} value={edit.provider_type} disabled={Boolean(edit.id)} onChange={(e) => setEdit({ ...edit, provider_type: e.target.value })} /></Field>
            <Field label={t('Provider name')}><Input placeholder={t('bhashini, twilio, console…')} value={edit.provider_name} disabled={Boolean(edit.id)} onChange={(e) => setEdit({ ...edit, provider_name: e.target.value })} /></Field>
          </div>
          <Field label={t('Settings (JSON, non-secret)')} hint={`${t('e.g.')} {"language": "mr"} ${t('or for Twilio')} {"from": "+1…"}`}><Textarea value={edit.config_text} onChange={(e) => setEdit({ ...edit, config_text: e.target.value })} /></Field>
          <Field label={t('Credentials (leave value blank to keep the stored one)')} group>
            <div className="space-y-2">
              {edit.creds.map((c, i) => (
                <div key={i} className="grid grid-cols-2 gap-2">
                  <Input placeholder={t('key')} value={c.key} onChange={(e) => setEdit({ ...edit, creds: edit.creds.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)) })} />
                  <Input type="password" placeholder={t('secret value')} value={c.value} onChange={(e) => setEdit({ ...edit, creds: edit.creds.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })} />
                </div>
              ))}
              <Button size="sm" variant="ghost" onClick={() => setEdit({ ...edit, creds: [...edit.creds, { key: '', value: '' }] })}>{t('Add credential')}</Button>
            </div>
          </Field>
          <div className="flex gap-4">
            <Checkbox label={t('Active')} checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
            <Checkbox label={t('Default for this type')} checked={edit.is_default} onChange={(e) => setEdit({ ...edit, is_default: e.target.checked })} />
          </div>
        </Modal>
      )}
    </Card>
  )
}

export default function Settings() {
  const [tab, setTab] = useState('lookups')
  return (
    <div>
      <PageHeader title={t('Configuration')} subtitle={t('Dropdown values, rules & thresholds, permissions and external providers. Every change is audit-logged.')} />
      <Tabs tabs={[{ value: 'lookups', label: t('Dropdown lists') }, { value: 'rules', label: t('Rules & thresholds') }, { value: 'permissions', label: t('Permissions') }, { value: 'providers', label: t('Providers') }]} value={tab} onChange={setTab} />
      {tab === 'lookups' && <Lookups />}
      {tab === 'rules' && <Rules />}
      {tab === 'permissions' && <Permissions />}
      {tab === 'providers' && <Providers />}
    </div>
  )
}
