import { BadgeCheck, MessageCircle, MessageSquare, Phone } from 'lucide-react'
import { Badge, Card, ErrorBox, PageHeader, Spinner, Table } from '../components/ui'
import { fmtDate, humanize } from '../lib/format'
import { useFetch, useLookups } from '../lib/hooks'
import { t } from '../lib/i18n'

export default function VolunteerContacts() {
  const categories = useLookups('contact_category')
  const { data, error, loading } = useFetch('/contacts', { page: 1, page_size: 100 })
  const contacts = data?.items || []
  const mandatory = ['hospital_head', 'police_patil', 'sarpanch', 'talathi']
  const byCategory = Object.fromEntries(contacts.map((contact) => [contact.category, contact]))
  return <div className="space-y-4">
    <PageHeader title={t('Village contacts')} subtitle={t('Key local support contacts for your assigned village. Contact details are maintained and verified by Stakeholders.')} />
    <ErrorBox message={error} />
    {loading && !data ? <Spinner /> : <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {mandatory.map((category) => {
          const contact = byCategory[category]
          return <Card key={category} title={t(humanize(category))}>
            <div className="min-h-16">{contact ? <><div className="font-medium text-gray-900">{contact.name}</div><div className="mt-1 text-sm text-gray-500">{contact.designation || contact.facility_name || ''}</div><a href={contact.quick_actions?.call || `tel:${contact.mobile}`} className="mt-2 inline-flex items-center gap-1.5 text-sm text-brand-700"><Phone className="h-4 w-4" />{contact.mobile}</a></> : <p className="text-sm text-gray-500">{t('Contact missing. Ask your Stakeholder to add it.')}</p>}</div>
            {contact && <div className="mt-3 flex items-center justify-between gap-2 border-t border-gray-100 pt-3">{contact.verified ? <span className="inline-flex items-center gap-1 text-xs text-green-700"><BadgeCheck className="h-4 w-4" />{t('Verified')} · {fmtDate(contact.verified_at)}</span> : <Badge tone="yellow">{t('Pending verification')}</Badge>}<div className="flex gap-2"><a aria-label={t('Call')} title={t('Call')} href={contact.quick_actions?.call || `tel:${contact.mobile}`}><Phone className="h-4 w-4 text-brand-700" /></a><a aria-label={t('SMS')} title={t('SMS')} href={contact.quick_actions?.sms || `sms:${contact.mobile}`}><MessageSquare className="h-4 w-4 text-brand-700" /></a><a aria-label={t('WhatsApp')} title={t('WhatsApp')} href={contact.quick_actions?.whatsapp || `https://wa.me/${contact.mobile}`} target="_blank" rel="noreferrer"><MessageCircle className="h-4 w-4 text-green-700" /></a></div></div>}
          </Card>
        })}
      </div>
      <Card title={t('All village contacts')} padded={false}>
        <Table columns={[
          { key: 'category', label: t('Role'), render: (row) => <span>{categories.find((item) => item.code === row.category)?.label || humanize(row.category)} {row.is_mandatory_category && <Badge tone="brand">{t('Required')}</Badge>}</span> },
          { key: 'name', label: t('Name'), className: 'font-medium' },
          { key: 'mobile', label: t('Mobile'), render: (row) => <span className="inline-flex items-center gap-2">{row.mobile}<a aria-label={t('Call')} href={row.quick_actions?.call || `tel:${row.mobile}`}><Phone className="h-4 w-4 text-brand-700" /></a><a aria-label={t('SMS')} href={row.quick_actions?.sms || `sms:${row.mobile}`}><MessageSquare className="h-4 w-4 text-brand-700" /></a><a aria-label={t('WhatsApp')} href={row.quick_actions?.whatsapp || `https://wa.me/${row.mobile}`} target="_blank" rel="noreferrer"><MessageCircle className="h-4 w-4 text-green-700" /></a></span> },
          { key: 'availability', label: t('Availability') },
          { key: 'verified', label: t('Verification'), render: (row) => <Badge tone={row.verified ? 'green' : 'yellow'}>{row.verified ? t('Verified') : t('Pending Stakeholder check')}</Badge> },
          { key: 'updated_at', label: t('Last updated'), render: (row) => fmtDate(row.updated_at) },
        ]} rows={contacts} empty={t('No contacts are listed for your village yet.')} />
      </Card>
    </>}
  </div>
}
