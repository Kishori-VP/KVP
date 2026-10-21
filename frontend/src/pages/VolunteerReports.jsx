import { Download, History, Printer } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button, Card, ErrorBox, PageHeader, ProgressBar, Spinner, StatusBadge, Table } from '../components/ui'
import { fmtDate, fmtDateTime, humanize, todayISO } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

function monthStart() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

function exportCsv(data) {
  if (!data) return
  const rows = [
    ['Type', 'Date', 'Title / activities', 'Status', 'Notes'],
    ...(data.visits || []).map((r) => ['Home visit', r.visit_date, r.purpose, r.status, r.observations || r.notes || '']),
    ...(data.activity_reports || []).map((r) => ['Daily report', r.report_date, (r.activities || []).join('; '), r.approval?.status || '', r.topics_discussed || '']),
    ...(data.events || []).map((r) => ['Event', r.start_at, r.title, r.status, r.report?.outcomes || '']),
    ...(data.targets || []).map((r) => ['Target', r.period_start, r.title, r.progress?.status || '', `${r.progress?.achieved || 0}/${r.target_value}`]),
  ]
  const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob(['\ufeff', csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = `KVP-volunteer-report-${data.start_date}-${data.end_date}.csv`
  document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url)
}

export default function VolunteerReports() {
  const [startDate, setStartDate] = useState(monthStart())
  const [endDate, setEndDate] = useState(todayISO())
  const report = useFetch('/volunteers/me/report', { start_date: startDate, end_date: endDate })
  const assignments = useFetch('/volunteers/me/assignment-history')
  const data = report.data
  useEffect(() => {
    const styleId = 'kvp-volunteer-report-print-style'
    if (document.getElementById(styleId)) return
    const style = document.createElement('style')
    style.id = styleId
    style.textContent = `
      @media print {
        @page { size: A4; margin: 12mm; }
        body * { visibility: hidden !important; }
        #volunteer-report-print, #volunteer-report-print * { visibility: visible !important; }
        #volunteer-report-print { position: absolute !important; inset: 0 auto auto 0 !important; width: 100% !important; padding: 0 !important; margin: 0 !important; background: white !important; color: black !important; }
        .no-print, #volunteer-report-print .no-print { display: none !important; }
        #volunteer-report-print .rounded-xl, #volunteer-report-print .rounded-lg { break-inside: avoid; box-shadow: none !important; }
        #volunteer-report-print table { width: 100% !important; border-collapse: collapse !important; font-size: 9pt !important; }
        #volunteer-report-print th, #volunteer-report-print td { border: 1px solid #bbb !important; padding: 5px !important; color: black !important; }
        #volunteer-report-print h1, #volunteer-report-print h2, #volunteer-report-print h3 { color: black !important; }
      }
    `
    document.head.appendChild(style)
    return () => { style.remove() }
  }, [])
  const summary = data?.summary || {}
  const metrics = [
    ['home_visits', 'Home visits'], ['girls_covered', 'Girls reached'], ['group_meetings', 'Group meetings'],
    ['events', 'Events conducted'], ['follow_ups', 'Follow-ups completed'], ['health_screenings', 'Health screenings'],
    ['case_closures', 'Cases resolved'], ['activity_reports', 'Daily reports submitted'],
  ]
  return <div className="space-y-4">
    <div><div className="no-print"><PageHeader title={t('My reports')} subtitle={t('Review your activity history, assigned targets and village assignment history.')} actions={<><Button variant="secondary" icon={Printer} onClick={() => window.print()}>{t('Print / Save PDF')}</Button><Button icon={Download} disabled={!data?.assigned} onClick={() => exportCsv(data)}>{t('Export CSV for Excel')}</Button></>} /></div>
    <div className="no-print"><Card title={t('Report period')}>
      <div className="grid gap-3 sm:grid-cols-3"><label className="text-xs font-medium text-gray-700">{t('From')}<input type="date" className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></label><label className="text-xs font-medium text-gray-700">{t('To')}<input type="date" className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" value={endDate} max={todayISO()} onChange={(e) => setEndDate(e.target.value)} /></label><div className="flex items-end"><Button variant="secondary" onClick={() => { setStartDate(monthStart()); setEndDate(todayISO()) }}>{t('This month')}</Button></div></div>
      <p className="mt-2 text-xs text-gray-500">{t('Reports are limited to your own activity and your assigned village.')}</p>
    </Card></div>
    <ErrorBox message={report.error} />
    {report.loading && !data ? <Spinner /> : data?.assigned === false ? <Card><p className="text-sm text-gray-600">{t('No village is assigned to your account yet.')}</p></Card> : <>
      <div id="volunteer-report-print" className="space-y-4 bg-white"><h1 className="mb-3 text-xl font-bold">{t('KVP Volunteer Activity Report')}</h1><p className="mb-4 text-sm">{t('Period')}: {startDate} – {endDate}</p><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{metrics.map(([key, label]) => <div key={key} className="rounded-xl border border-black/10 bg-white p-4"><div className="text-xs text-gray-500">{t(label)}</div><div className="mt-1 text-2xl font-semibold text-gray-900">{summary[key] || 0}</div></div>)}</div>
      <Card title={t('Target progress')}>
        <Table columns={[
          { key: 'title', label: t('Target'), className: 'font-medium' },
          { key: 'period', label: t('Period'), render: (r) => `${fmtDate(r.period_start)} – ${fmtDate(r.period_end)}` },
          { key: 'progress', label: t('Progress'), render: (r) => <div className="min-w-28"><ProgressBar pct={r.progress?.progress_pct} /><span className="text-xs text-gray-500">{r.progress?.achieved || 0} / {r.target_value}</span></div> },
          { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.progress?.status} /> },
        ]} rows={data?.targets || []} empty={t('No targets overlap this report period.')} />
      </Card>
      <Card title={t('Home visit history')}>
        <Table columns={[
          { key: 'visit_date', label: t('Date'), render: (r) => fmtDate(r.visit_date) },
          { key: 'purpose', label: t('Purpose'), render: (r) => humanize(r.purpose) },
          { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
          { key: 'girls', label: t('Girls reached'), render: (r) => r.girl_ids?.length || 0 },
          { key: 'approval', label: t('Review'), render: (r) => <StatusBadge value={r.approval?.status} /> },
        ]} rows={data?.visits || []} empty={t('No visits in this report period.')} />
      </Card>
      <Card title={t('Daily activity reports')}>
        <Table columns={[
          { key: 'report_date', label: t('Date'), render: (r) => fmtDate(r.report_date) },
          { key: 'activities', label: t('Activities'), render: (r) => (r.activities || []).map(humanize).join(', ') || '—' },
          { key: 'groups', label: t('Groups'), render: (r) => r.group_ids?.length || 0 },
          { key: 'girls_present', label: t('Girls present') },
          { key: 'home_visits_count', label: t('Visits') },
          { key: 'approval', label: t('Review'), render: (r) => <StatusBadge value={r.approval?.status} /> },
        ]} rows={data?.activity_reports || []} empty={t('No daily reports in this period.')} />
      </Card>
      <Card title={t('Events you were responsible for')}>
        <Table columns={[
          { key: 'title', label: t('Event'), className: 'font-medium' },
          { key: 'start_at', label: t('Date'), render: (r) => fmtDateTime(r.start_at) },
          { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
          { key: 'report', label: t('Report'), render: (r) => r.report ? <StatusBadge value={r.approval?.status || 'submitted'} /> : <StatusBadge value="pending" /> },
        ]} rows={data?.events || []} empty={t('No assigned events in this period.')} />
      </Card>
      <Card title={t('Village assignment history')}>
        <div className="mb-3 flex items-center gap-2 text-xs text-gray-500"><History className="h-4 w-4" />{t('Previous village assignments are retained for accountability.')}</div>
        <ErrorBox message={assignments.error} />
        {assignments.loading && !assignments.data ? <Spinner /> : <Table columns={[
          { key: 'village_name', label: t('Village'), className: 'font-medium' },
          { key: 'start_date', label: t('Assigned from'), render: (r) => fmtDate(r.start_date) },
          { key: 'end_date', label: t('Assigned until'), render: (r) => r.end_date ? fmtDate(r.end_date) : t('Current assignment') },
          { key: 'reason', label: t('Reason') },
        ]} rows={assignments.data || []} empty={t('No assignment history has been recorded yet.')} />}
      </Card></div>
    </>}
    </div>
  </div>
}
