import { AlertTriangle, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { t } from '../lib/i18n'
import { Button, Field, Modal, Textarea } from './ui'

let showDialog = null

/**
 * Ask before deleting. Resolves to false when cancelled.
 * Without `reason`, resolves to true when confirmed.
 * With `reason` (the default text), the popup also asks for a reason and resolves to the entered text.
 */
export function confirmDelete({ title, message, reason } = {}) {
  if (!showDialog) return Promise.resolve(window.confirm(`${message || ''}\n\n${t('This cannot be retrieved once deleted.')}`) && (reason ?? true))
  return new Promise((resolve) => showDialog({ title, message, reason, resolve }))
}

/** Mount once near the app root; renders the popup opened by confirmDelete(). */
export function ConfirmDeleteHost() {
  const [dlg, setDlg] = useState(null)
  const [reason, setReason] = useState('')
  useEffect(() => {
    showDialog = (d) => { setReason(d.reason ?? ''); setDlg(d) }
    return () => { showDialog = null }
  }, [])
  if (!dlg) return null
  const askReason = dlg.reason !== undefined
  const close = (value) => { dlg.resolve(value); setDlg(null) }
  // Wrapped so it sits above any modal it was opened from.
  return (
    <div className="relative z-[60]">
    <Modal open title={dlg.title || t('Delete permanently?')} onClose={() => close(false)}
      footer={<>
        <Button variant="secondary" onClick={() => close(false)}>{t('Cancel')}</Button>
        <Button variant="danger" icon={Trash2} disabled={askReason && !reason.trim()} onClick={() => close(askReason ? reason.trim() : true)}>{t('Yes, delete')}</Button>
      </>}>
      {dlg.message && <p className="text-sm text-gray-700">{dlg.message}</p>}
      <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm font-medium text-red-800">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{t('This cannot be retrieved once deleted.')}</span>
      </div>
      {askReason && <Field label={t('Reason for deleting *')}><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
    </Modal>
    </div>
  )
}
