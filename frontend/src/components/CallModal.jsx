import {
  Check,
  CheckCircle2,
  Copy,
  Info,
  Phone,
  PhoneCall,
} from 'lucide-react'
import { useState } from 'react'
import {
  Badge,
  Button,
  Card,
  Checkbox,
  ErrorBox,
  Field,
  Input,
  Modal,
  Select,
} from './ui'
import VoiceTextarea from './VoiceTextarea'
import api from '../lib/api'
import { fmtDate, humanize, todayISO } from '../lib/format'
import { useAction, useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

const CALL_STATUSES = [
  { value: 'completed', label: 'Completed (पूर्ण)' },
  { value: 'planned', label: 'Planned (नियोजित)' },
  { value: 'unanswered', label: 'Unanswered / Not picked (उचलला नाही)' },
  { value: 'busy', label: 'Busy (व्यस्त)' },
  { value: 'wrong_number', label: 'Wrong number (चुकीचा नंबर)' },
]

const CALL_PURPOSES = [
  { value: 'routine', label: 'Routine check-in (नियमित चौकशी)' },
  { value: 'follow_up', label: 'Follow-up (पुढील पाठपुरावा)' },
  { value: 'case_follow_up', label: 'Case follow-up (केस पाठपुरावा)' },
  { value: 'enrolment', label: 'Enrolment / Mobilisation (नोंदणी / प्रवेश)' },
  { value: 'counseling', label: 'Counseling & Guidance (समुपदेशन व मार्गदर्शन)' },
  { value: 'health', label: 'Health & Nutrition (आरोग्य व पोषण)' },
  { value: 'other', label: 'Other (इतर)' },
]

const RISK_KEYS = [
  ['child_marriage_risk', 'Child marriage risk (बालविवाह धोका)'],
  ['school_dropout_risk', 'School dropout risk (शाळा सोडण्याचा धोका)'],
  ['health_concern', 'Health concern (आरोग्य समस्या)'],
  ['anaemia_concern', 'Anaemia concern (अ‍ॅनिमिया चिंता)'],
  ['gender_discrimination', 'Gender discrimination (लैंगिक भेदभाव)'],
]

export default function CallModal({ externalGirl, onClose, onSaved }) {
  // Query only girls not called in the last 30 days
  const { data: girlList, reload: reloadGirls } = useFetch(
    '/external-girls',
    { eligible_for_call: true, page: 1, page_size: 500 }
  )

  const oneMonthAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString()
  const rawList = girlList?.items || []

  // Ensure passed girl is selectable even if recently called
  const eligibleGirls = externalGirl && !rawList.some((g) => g.id === externalGirl.id)
    ? [externalGirl, ...rawList]
    : rawList

  const [selectedGirlId, setSelectedGirlId] = useState(
    externalGirl?.id || (eligibleGirls.length > 0 ? eligibleGirls[0].id : '')
  )

  const selectedGirl =
    (externalGirl && externalGirl.id === selectedGirlId ? externalGirl : null) ||
    eligibleGirls.find((g) => g.id === selectedGirlId)

  const [phoneOverride, setPhoneOverride] = useState('')
  const [copied, setCopied] = useState(false)

  const currentPhone = phoneOverride || selectedGirl?.phone || ''

  const [form, setForm] = useState({
    call_date: todayISO(),
    status: 'completed',
    purpose: 'routine',
    observations: '',
    notes: '',
  })

  const [risks, setRisks] = useState({
    child_marriage_risk: false,
    school_dropout_risk: false,
    health_concern: false,
    anaemia_concern: false,
    gender_discrimination: false,
    other: '',
  })

  // Prior call history for the selected girl
  const { data: priorCalls } = useFetch(
    selectedGirlId ? `/external-calls` : null,
    { external_girl_id: selectedGirlId, page: 1, page_size: 3 }
  )

  const { busy, error, run } = useAction()

  const copyPhone = async () => {
    if (!currentPhone) return
    try {
      await navigator.clipboard.writeText(currentPhone)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback
    }
  }

  const save = () =>
    run(async () => {
      // If phone was entered/updated, update the girl doc as well
      if (phoneOverride && phoneOverride !== selectedGirl?.phone) {
        try {
          await api.patch(`/external-girls/${selectedGirlId}`, { phone: phoneOverride })
        } catch {}
      }

      await api.post('/external-calls', {
        external_girl_id: selectedGirlId,
        call_date: form.call_date,
        status: form.status,
        purpose: form.purpose,
        phone_called: currentPhone || null,
        risk_indicators: risks,
        observations: form.observations,
        notes: form.notes,
      })
      onSaved()
    })

  return (
    <Modal
      open
      title={
        form.status === 'planned'
          ? t('Plan a call to external girl')
          : t('Record a call with external girl')
      }
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('Cancel')}
          </Button>
          <Button
            busy={busy}
            icon={PhoneCall}
            disabled={!selectedGirlId || !form.call_date}
            onClick={save}
          >
            {form.status === 'planned' ? t('Save planned call') : t('Save call record')}
          </Button>
        </>
      }
    >
      <ErrorBox message={error} />

      <div className="space-y-4">
        {/* Selection: Only girls not called within the last 30 days appear */}
        <div>
          <Field
            label={t('Select an external girl (किशोरी निवडा) *')}
            hint={t('Girls called within the last 1 month are hidden so all girls get their turn.')}
          >
            {eligibleGirls.length === 0 ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                <Info className="mb-1 inline-block h-4 w-4 text-amber-700 mr-1" />
                {t('All external girls have been called within the last 30 days! Every girl has had her turn.')}
              </div>
            ) : (
              <select
                className="w-full rounded-lg border border-gray-300 bg-white p-2.5 text-sm font-medium focus:border-brand-500 focus:outline-none"
                value={selectedGirlId}
                onChange={(e) => {
                  setSelectedGirlId(e.target.value)
                  setPhoneOverride('')
                }}
              >
                {eligibleGirls.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name} — {g.location || 'गावाचे ठिकाण नाही'} {g.standard ? `(${g.standard})` : ''}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>

        {/* Selected Girl Summary & Phone Call / Copy Section */}
        {selectedGirl && (
          <div className="rounded-xl border border-gray-200 bg-gray-50/80 p-3.5 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-base font-semibold text-gray-900">
                  {selectedGirl.name}
                </div>
                <div className="text-xs text-gray-500">
                  {selectedGirl.location ? `${selectedGirl.location} · ` : ''}
                  {selectedGirl.standard ? `${selectedGirl.standard} · ` : ''}
                  {selectedGirl.school_or_college || ''}
                </div>
              </div>

              {/* Copy / Call Phone Button */}
              {currentPhone ? (
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex items-center rounded-lg border border-gray-300 bg-white px-2.5 py-1.5 shadow-xs">
                    <span className="font-mono text-sm font-bold text-gray-800 mr-2">
                      {currentPhone}
                    </span>
                    <button
                      type="button"
                      onClick={copyPhone}
                      className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-xs font-semibold text-gray-700 hover:bg-gray-200"
                      title={t('Copy phone number')}
                    >
                      {copied ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                          <span className="text-emerald-700">{t('Copied!')}</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5 text-gray-600" />
                          <span>{t('Copy')}</span>
                        </>
                      )}
                    </button>
                  </div>

                  <a
                    href={`tel:${currentPhone}`}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white shadow hover:bg-emerald-700 active:scale-95"
                    title={t('Click to call directly on phone')}
                  >
                    <PhoneCall className="h-3.5 w-3.5" />
                    <span>{t('Call')}</span>
                  </a>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-xs">
                  <Input
                    type="tel"
                    placeholder={t('Enter phone number')}
                    value={phoneOverride}
                    onChange={(e) => setPhoneOverride(e.target.value)}
                    className="w-36 text-xs"
                  />
                  {phoneOverride && (
                    <button
                      type="button"
                      onClick={copyPhone}
                      className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs font-semibold"
                    >
                      {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                      <span>{copied ? t('Copied') : t('Copy')}</span>
                    </button>
                  )}
                  {phoneOverride && (
                    <a
                      href={`tel:${phoneOverride}`}
                      className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-xs font-bold text-white shadow"
                    >
                      <PhoneCall className="h-3.5 w-3.5" />
                      <span>{t('Call')}</span>
                    </a>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Form Inputs: Date, Status, Purpose (Duration REMOVED as requested) */}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t('Call date *')}>
            <Input
              type="date"
              value={form.call_date}
              onChange={(e) => setForm({ ...form, call_date: e.target.value })}
            />
          </Field>

          <Field label={t('Call status (कॉल स्थिती) *')}>
            <Select
              options={CALL_STATUSES}
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            />
          </Field>

          <Field label={t('Call purpose (उद्देश) *')}>
            <Select
              options={CALL_PURPOSES}
              value={form.purpose}
              onChange={(e) => setForm({ ...form, purpose: e.target.value })}
            />
          </Field>
        </div>

        {/* Prior Call History for this girl */}
        {selectedGirlId && (
          <Card title={t('Recent call history for selected girl')}>
            <div className="space-y-2">
              {(priorCalls?.items || []).map((call) => (
                <div key={call.id} className="rounded-lg bg-gray-50 p-2.5 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-1 font-medium text-gray-800">
                    <span>
                      {fmtDate(call.call_date)} · {humanize(call.purpose)} · {humanize(call.status)}
                    </span>
                    <span className="text-gray-500">{call.caller_name}</span>
                  </div>
                  <div className="mt-1 whitespace-pre-wrap text-gray-600">
                    {call.observations || call.notes || t('No observations recorded.')}
                  </div>
                </div>
              ))}
              {!priorCalls?.items?.length && (
                <p className="text-xs text-gray-500">
                  {t('No previous calls recorded for this girl.')}
                </p>
              )}
            </div>
          </Card>
        )}

        {/* Risk Indicators (same as house visit) */}
        <Field label={t('Risk indicators (धोका निर्देशक)')}>
          <div className="flex flex-wrap gap-3">
            {RISK_KEYS.map(([key, label]) => (
              <Checkbox
                key={key}
                label={t(label)}
                checked={Boolean(risks[key])}
                onChange={(e) => setRisks({ ...risks, [key]: e.target.checked })}
              />
            ))}
          </div>
        </Field>

        {/* Observations: Speech to Text (NO PLACEHOLDER as requested) */}
        <VoiceTextarea
          label={t('Observations during call (कॉल दरम्यान नोंदवलेली निरीक्षणे)')}
          value={form.observations}
          onChange={(val) => setForm({ ...form, observations: val })}
        />

        {/* Notes / Next steps: Speech to Text (NO PLACEHOLDER as requested) */}
        <VoiceTextarea
          label={t('Notes / Next steps (पुढील पावले / नोंदी)')}
          value={form.notes}
          onChange={(val) => setForm({ ...form, notes: val })}
        />
      </div>
    </Modal>
  )
}
