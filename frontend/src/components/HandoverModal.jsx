import { ArrowRightLeft } from 'lucide-react'
import { useEffect, useState } from 'react'
import { todayISO } from '../lib/format'
import { invalidateRefData, useAction, useFetch } from '../lib/hooks'
import { bilingual, t } from '../lib/i18n'
import api from '../lib/api'
import { Button, Checkbox, ErrorBox, Field, Input, Modal, Select, Spinner } from './ui'

export default function HandoverModal({
  open,
  onClose,
  onDone,
  sourceVolunteer = null,
  villageId = null,
}) {
  const { data: volunteersList, loading: volsLoading } = useFetch(open ? '/volunteers' : null, { is_active: true })
  const activeVolunteers = Array.isArray(volunteersList) ? volunteersList : []

  const [fromVolId, setFromVolId] = useState(sourceVolunteer?.id || '')
  const [selectedVid, setSelectedVid] = useState(villageId || sourceVolunteer?.village_id || '')
  const [toVolId, setToVolId] = useState('')
  const [transferGroups, setTransferGroups] = useState(true)
  const [transferCases, setTransferCases] = useState(true)
  const [effectiveDate, setEffectiveDate] = useState(todayISO())
  const [reason, setReason] = useState('')

  // Selected source volunteer object
  const currentSource = sourceVolunteer?.id === fromVolId
    ? sourceVolunteer
    : activeVolunteers.find((v) => String(v.id) === String(fromVolId))

  // Find assigned villages for current source volunteer
  const { data: detailedSource } = useFetch(
    open && fromVolId && (!currentSource?.villages?.length && currentSource?.id !== sourceVolunteer?.id)
      ? `/volunteers/${fromVolId}`
      : null
  )

  const sourceData = detailedSource || currentSource

  const availableVillages = (() => {
    if (!sourceData) return []
    if (Array.isArray(sourceData.villages) && sourceData.villages.length > 0) {
      return sourceData.villages.map((v) => ({
        value: String(v.id || v._id),
        label: bilingual(v.name, v.name_mr),
      }))
    }
    if (sourceData.village_id) {
      return [{
        value: String(sourceData.village_id),
        label: bilingual(sourceData.village?.name || sourceData.village_name, sourceData.village?.name_mr || sourceData.village_name_mr),
      }]
    }
    return []
  })()

  // Auto-select village if only 1 village exists or current selection invalid
  useEffect(() => {
    if (availableVillages.length > 0) {
      const match = availableVillages.find((v) => v.value === String(selectedVid))
      if (!match) {
        setSelectedVid(availableVillages[0].value)
      }
    } else {
      setSelectedVid('')
    }
  }, [fromVolId, availableVillages.length])

  // Reset target volunteer if same as source or already has this village
  useEffect(() => {
    if (toVolId === fromVolId) {
      setToVolId('')
    }
  }, [fromVolId])

  // Filter eligible target Tais (exclude source and any volunteer already in selectedVid)
  const targetTaiOptions = activeVolunteers
    .filter((v) => {
      if (String(v.id) === String(fromVolId)) return false
      if (selectedVid) {
        const vIds = [v.village_id, ...(v.village_ids || [])].map((id) => String(id))
        if (vIds.includes(String(selectedVid))) return false
      }
      return true
    })
    .map((v) => {
      const currentVName = v.village_name ? ` (${bilingual(v.village_name, v.village_name_mr)})` : ''
      return {
        value: String(v.id),
        label: `${bilingual(v.name, v.name_mr)}${currentVName}`,
      }
    })

  const { busy, error, run } = useAction()

  const submit = () =>
    run(async () => {
      await api.post('/volunteers/handover', {
        from_volunteer_id: fromVolId,
        to_volunteer_id: toVolId,
        village_id: selectedVid,
        transfer_groups: transferGroups,
        transfer_cases: transferCases,
        effective_date: effectiveDate || null,
        reason: reason.trim(),
      })

      invalidateRefData()
      if (onDone) onDone()
      onClose()
    }).catch(() => {})

  const fromTaiOptions = activeVolunteers
    .filter((v) => v.village_id || (Array.isArray(v.village_ids) && v.village_ids.length > 0))
    .map((v) => ({
      value: String(v.id),
      label: `${bilingual(v.name, v.name_mr)} (${bilingual(v.village_name || 'No village', v.village_name_mr)})`,
    }))

  const canSubmit = Boolean(fromVolId && selectedVid && toVolId && reason.trim().length >= 3)

  return (
    <Modal
      open={open}
      title={t('Handover Village Responsibility')}
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('Cancel')}
          </Button>
          <Button
            busy={busy}
            icon={ArrowRightLeft}
            disabled={!canSubmit}
            onClick={submit}
            className="bg-brand-700 hover:bg-brand-800 text-white"
          >
            {t('Confirm Handover')}
          </Button>
        </>
      }
    >
      <ErrorBox message={error} />

      <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-3 text-xs sm:text-sm text-blue-900 space-y-1">
        <p className="font-semibold">{t('Village Handover Between Tais')}</p>
        <p className="text-xs text-blue-800">
          {t(
            'Transfer village responsibility from one Tai to another. The source Tai’s assignment for this village will be closed in history, and a new assignment will be started for the target Tai.'
          )}
        </p>
      </div>

      {volsLoading && !activeVolunteers.length ? (
        <Spinner />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {/* Source Tai */}
            <Field label={t('From Tai (Handing over) *')}>
              {sourceVolunteer ? (
                <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-medium text-gray-800">
                  {bilingual(sourceVolunteer.name, sourceVolunteer.name_mr)}
                </div>
              ) : (
                <Select
                  options={fromTaiOptions}
                  placeholder={t('Select source Tai')}
                  value={fromVolId}
                  onChange={(e) => setFromVolId(e.target.value)}
                />
              )}
            </Field>

            {/* Village to Handover */}
            <Field label={t('Village to Handover *')}>
              {availableVillages.length <= 1 && availableVillages[0] ? (
                <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm font-medium text-gray-800">
                  {availableVillages[0].label}
                </div>
              ) : (
                <Select
                  options={availableVillages}
                  placeholder={t('Select village to handover')}
                  value={selectedVid}
                  disabled={!fromVolId || availableVillages.length === 0}
                  onChange={(e) => setSelectedVid(e.target.value)}
                />
              )}
            </Field>
          </div>

          {/* Target Tai */}
          <Field label={t('To Tai (Recipient) *')} hint={t('Select the Tai taking over responsibility for this village.')}>
            <Select
              options={targetTaiOptions}
              placeholder={t('Select recipient Tai')}
              value={toVolId}
              disabled={!selectedVid}
              onChange={(e) => setToVolId(e.target.value)}
            />
          </Field>

          {/* Transfer Options */}
          <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-3 space-y-2">
            <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
              {t('Included in Handover')}
            </div>

            <Checkbox
              checked={transferGroups}
              onChange={(e) => setTransferGroups(e.target.checked)}
              label={t('Transfer Kishori Groups of this village to new Tai')}
            />

            <Checkbox
              checked={transferCases}
              onChange={(e) => setTransferCases(e.target.checked)}
              label={t('Transfer open beneficiary cases in this village to new Tai')}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {/* Effective Date */}
            <Field label={t('Handover Date')}>
              <Input
                type="date"
                value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)}
              />
            </Field>

            {/* Handover Reason */}
            <Field label={t('Reason for Handover *')}>
              <Input
                placeholder={t('e.g. Area reallocation, medical leave, or workload balance')}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
          </div>
        </div>
      )}
    </Modal>
  )
}
