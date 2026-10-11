import { BadgeCheck, MessageCircle, MessageSquare, Phone, Plus } from 'lucide-react'
import { useState } from 'react'
import { LookupSelect, TalukaSelect, VillageSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Spinner, Table, Tabs, Textarea } from '../components/ui'
import api from '../lib/api'
import { fmtDate, humanize } from '../lib/format'
import { lookupLabel, useAction, useFetch, useLookups, useVillages } from '../lib/hooks'
import { t } from '../lib/i18n'

function ContactModal({ contact, onClose, onSaved }) {
  const [f, setF] = useState(contact || {})
  const { busy, error, run } = useAction()
  const save = () => run(async () => {
    const body = Object.fromEntries(['category', 'name', 'designation', 'facility_name', 'mobile', 'alternate_mobile', 'availability', 'notes'].map((k) => [k, f[k] || null]))
    if (contact) await api.patch(`/contacts/${contact.id}`, body)
    else await api.post('/contacts', { ...body, village_id: f.village_id })
    onSaved()
  }).catch(() => {})
  return (
    <Modal open title={contact ? t('Edit {code}', { code: contact.name }) : t('Add contact')} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={!f.name || !f.mobile || !f.category || !f.village_id} onClick={save}>{t('Save')}</Button></>}>
      <ErrorBox message={error} />
      {contact && <p className="text-xs text-gray-500">{t('Changing the name, mobile or role resets verification.')}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        {!contact && <Field label={t('Village *')}><VillageSelect value={f.village_id} onChange={(v) => setF({ ...f, village_id: v })} placeholder={t('Select')} /></Field>}
        <Field label={t('Role *')}><LookupSelect type="contact_category" value={f.category} onChange={(v) => setF({ ...f, category: v })} /></Field>
        <Field label={t('Name *')}><Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('Designation')}><Input value={f.designation || ''} onChange={(e) => setF({ ...f, designation: e.target.value })} /></Field>
        {f.category === 'hospital_head' && <Field label={t('Hospital / clinic name')}><Input value={f.facility_name || ''} onChange={(e) => setF({ ...f, facility_name: e.target.value })} /></Field>}
        <Field label={t('Mobile *')}><Input value={f.mobile || ''} onChange={(e) => setF({ ...f, mobile: e.target.value })} /></Field>
        <Field label={t('Alternate number')}><Input value={f.alternate_mobile || ''} onChange={(e) => setF({ ...f, alternate_mobile: e.target.value })} /></Field>
        <Field label={t('Availability')}><Input placeholder={t('Mon–Sat 10am–5pm')} value={f.availability || ''} onChange={(e) => setF({ ...f, availability: e.target.value })} /></Field>
      </div>
      <Field label={t('Notes')}><Textarea value={f.notes || ''} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
    </Modal>
  )
}

function Directory() {
  const [f, setF] = useState({ village_id: '', taluka_id: '', category: '', q: '', verified: '' })
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const cats = useLookups('contact_category')
  const villages = useVillages()
  const { data, error, loading, reload } = useFetch('/contacts', { ...f, page, page_size: 50 })
  const verify = async (c) => { await api.post(`/contacts/${c.id}/verify`); reload() }
  const set = (k, v) => { setF({ ...f, [k]: v }); setPage(1) }
  return (
    <Card padded={false} title={t('Village support directory')} actions={<Button size="sm" icon={Plus} onClick={() => setModal('new')}>{t('Add contact')}</Button>}>
      <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-5">
        <Input placeholder={t('Search name, mobile…')} value={f.q} onChange={(e) => set('q', e.target.value)} />
        <TalukaSelect value={f.taluka_id} onChange={(v) => set('taluka_id', v)} />
        <VillageSelect value={f.village_id} talukaId={f.taluka_id} onChange={(v) => set('village_id', v)} />
        <LookupSelect type="contact_category" value={f.category} onChange={(v) => set('category', v)} placeholder={t('Any role')} />
        <select className="rounded-lg border border-gray-300 px-3 py-2 text-sm" value={f.verified} onChange={(e) => set('verified', e.target.value)}>
          <option value="">{t('Verified & unverified')}</option><option value="true">{t('Verified')}</option><option value="false">{t('Unverified')}</option>
        </select>
      </div>
      <ErrorBox message={error} />
      {loading && !data ? <Spinner /> : (
        <>
          <Table columns={[
            { key: 'village', label: t('Village'), render: (c) => villages.find((v) => v.id === c.village_id)?.name || '—' },
            { key: 'category', label: t('Role'), render: (c) => <span>{lookupLabel(cats, c.category)} {c.is_mandatory_category && <Badge tone="brand">{t('Key')}</Badge>}</span> },
            { key: 'name', label: t('Name'), render: (c) => <span className="font-medium">{c.name}{c.facility_name && <span className="block text-xs text-gray-500">{c.facility_name}</span>}</span> },
            { key: 'mobile', label: t('Contact'), render: (c) => (
              <span className="inline-flex items-center gap-2 whitespace-nowrap">{c.mobile}
                <a href={c.quick_actions.call} title={t('Call')} className="rounded p-1 hover:bg-brand-50"><Phone className="h-4 w-4 text-brand-700" /></a>
                <a href={c.quick_actions.sms} title={t('SMS')} className="rounded p-1 hover:bg-brand-50"><MessageSquare className="h-4 w-4 text-brand-700" /></a>
                <a href={c.quick_actions.whatsapp} target="_blank" rel="noreferrer" title={t('WhatsApp')} className="rounded p-1 hover:bg-green-50"><MessageCircle className="h-4 w-4 text-green-700" /></a>
              </span>) },
            { key: 'availability', label: t('Availability') },
            { key: 'verified', label: t('Verification'), render: (c) => (c.verified
              ? <span className="text-xs text-green-800"><BadgeCheck className="mr-1 inline h-4 w-4" />{fmtDate(c.verified_at)}</span>
              : <Button size="sm" variant="secondary" onClick={() => verify(c)}>{t('Verify')}</Button>) },
            { key: 'updated_at', label: t('Updated'), render: (c) => fmtDate(c.updated_at) },
            { key: 'edit', label: '', render: (c) => <Button size="sm" variant="ghost" onClick={() => setModal(c)}>{t('Edit')}</Button> },
          ]} rows={data?.items} empty={t('No contacts yet. Each village needs its hospital/clinic head, Police Patil, Sarpanch and Talathi.')} />
          <Pagination page={page} pageSize={50} total={data?.total} onPage={setPage} />
        </>
      )}
      {modal && <ContactModal contact={modal === 'new' ? null : modal} onClose={() => setModal(null)} onSaved={() => { setModal(null); reload() }} />}
    </Card>
  )
}

function Coverage() {
  const { data } = useFetch('/contacts/coverage')
  if (!data) return <Spinner />
  return (
    <Card title={t('Key contact coverage · {a} of {b} villages complete & verified', { a: data.villages_complete, b: data.villages_total })}>
      <Table rowKey={(r) => r.village_id} columns={[
        { key: 'village_name', label: t('Village'), className: 'font-medium' },
        { key: 'missing', label: t('Missing'), render: (r) => r.missing.map(humanize).join(', ') || '—' },
        { key: 'unverified', label: t('Unverified'), render: (r) => r.unverified.map(humanize).join(', ') || '—' },
        { key: 'complete', label: t('Status'), render: (r) => (r.complete ? <Badge tone="green">{t('Complete')}</Badge> : <Badge tone="yellow">{t('Incomplete')}</Badge>) },
      ]} rows={data.villages} />
    </Card>
  )
}

export default function Contacts() {
  const [tab, setTab] = useState('directory')
  return (
    <div>
      <PageHeader title={t('Contacts')} subtitle={t('Hospital/clinic head, Police Patil, Sarpanch, Talathi and other support contacts per village')} />
      <Tabs tabs={['directory', 'coverage']} value={tab} onChange={setTab} />
      {tab === 'directory' ? <Directory /> : <Coverage />}
    </div>
  )
}
