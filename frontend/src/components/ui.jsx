import { AlertCircle, ChevronLeft, ChevronRight, Loader2, X } from 'lucide-react'
import { useEffect } from 'react'
import { humanize } from '../lib/format'
import { locale, t } from '../lib/i18n'

export function cx(...classes) {
  return classes.filter(Boolean).join(' ')
}

const BTN = {
  primary: 'bg-brand-gradient bg-brand-gradient-hover text-white',
  secondary: 'border border-gray-200 bg-white text-gray-800 shadow-sm hover:border-brand-200 hover:bg-brand-50 disabled:text-gray-400',
  danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
  ghost: 'text-brand-700 hover:bg-brand-50 disabled:text-gray-400',
}

export function Button({ variant = 'primary', size = 'md', busy, className, children, icon: Icon, ...props }) {
  return (
    <button
      type="button"
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:cursor-not-allowed',
        size === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm',
        BTN[variant],
        className,
      )}
      disabled={busy || props.disabled}
      {...props}
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </button>
  )
}

export function Card({ title, actions, children, className, padded = true }) {
  return (
    <section className={cx('overflow-hidden rounded-2xl border border-gray-200/80 bg-white shadow-sm shadow-slate-900/[0.03]', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 bg-gradient-to-r from-brand-50/60 to-white px-4 py-3">
          {title && <h2 className="text-sm font-semibold tracking-[-0.01em] text-gray-900">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-gray-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm leading-relaxed text-gray-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

const TONES = {
  gray: 'bg-gray-100 text-gray-700',
  brand: 'bg-brand-100 text-brand-800',
  green: 'bg-green-100 text-green-800',
  yellow: 'bg-amber-100 text-amber-800',
  orange: 'bg-orange-100 text-orange-800',
  red: 'bg-red-100 text-red-800',
  blue: 'bg-blue-100 text-blue-800',
}

const STATUS_TONE = {
  active: 'green', approved: 'green', completed: 'green', achieved: 'green', on_track: 'green', synced: 'green',
  verified: 'green', resolved: 'green', normal: 'green', sent: 'green', logged: 'green', closed: 'gray',
  upcoming: 'blue', scheduled: 'blue', planned: 'blue', today: 'brand', open: 'blue', in_progress: 'brand',
  pending: 'yellow', at_risk: 'yellow', delayed: 'yellow', mild: 'yellow', medium: 'yellow', skipped: 'gray',
  overdue: 'orange', escalated: 'orange', high: 'orange', moderate: 'orange', inactive: 'gray', cancelled: 'gray',
  missed: 'red', rejected: 'red', critical: 'red', severe: 'red', failed: 'red', no_recent_activity: 'red', low: 'gray',
}

export function Badge({ tone, children }) {
  return <span className={cx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium', TONES[tone || 'gray'])}>{children}</span>
}

/** Badge whose colour follows a status code; always shows the text label (never colour alone). */
export function StatusBadge({ value }) {
  if (value === null || value === undefined) return <span className="text-gray-400">—</span>
  return <Badge tone={STATUS_TONE[value] || 'gray'}>{t(humanize(value))}</Badge>
}

/**
 * Labelled form control. Use `group` when wrapping several controls (checkbox lists,
 * chips, key/value rows): it renders a fieldset instead of a <label>, because nested
 * labels are invalid HTML and make clicks toggle the wrong control.
 */
export function Field({ label, hint, children, className, group }) {
  if (group) {
    return (
      <fieldset className={cx('block', className)}>
        {label && <legend className="mb-1 block text-xs font-medium text-gray-700">{label}</legend>}
        {children}
        {hint && <span className="mt-1 block text-xs text-gray-500">{hint}</span>}
      </fieldset>
    )
  }
  return (
    <label className={cx('block', className)}>
      {label && <span className="mb-1 block text-xs font-medium text-gray-700">{label}</span>}
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-500">{hint}</span>}
    </label>
  )
}

const INPUT = 'w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm shadow-sm outline-none transition placeholder:text-gray-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-gray-50'

export function Input(props) {
  return <input className={INPUT} {...props} />
}

export function Textarea(props) {
  return <textarea className={INPUT} rows={3} {...props} />
}

/** options: [{value, label}] or strings */
export function Select({ options = [], placeholder, ...props }) {
  return (
    <select className={INPUT} {...props}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => {
        const opt = typeof o === 'string' ? { value: o, label: humanize(o) } : o
        return (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        )
      })}
    </select>
  )
}

export function Checkbox({ label, ...props }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-gray-700">
      <input type="checkbox" className="h-4 w-4 rounded border-gray-300 text-brand-600" {...props} />
      {label}
    </label>
  )
}

export function Spinner({ label = t('Loading…') }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-gray-500 justify-center">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  )
}

export function ErrorBox({ message }) {
  if (!message) return null
  return (
    <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  )
}

export function Empty({ children = t('Nothing to show yet.') }) {
  return <div className="py-8 text-center text-sm text-gray-500">{children}</div>
}

/**
 * columns: [{key, label, render?(row), className?}]
 */
export function Table({ columns, rows, onRowClick, empty, rowKey = (r) => r.id }) {
  if (!rows?.length) return <Empty>{empty}</Empty>
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
            {columns.map((c) => (
              <th key={c.key} className={cx('px-3 py-2 font-medium whitespace-nowrap', c.className)}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKey(row) ?? i}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cx('border-b border-gray-100 last:border-0', onRowClick && 'cursor-pointer hover:bg-brand-50/60')}
            >
              {columns.map((c) => (
                <td key={c.key} className={cx('px-3 py-2 align-top', c.className)}>
                  {c.render ? c.render(row) : (row[c.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({ page, pageSize, total, onPage }) {
  if (!total || total <= pageSize) return null
  const pages = Math.ceil(total / pageSize)
  return (
    <div className="flex items-center justify-between border-t border-gray-100 px-3 py-2 text-sm text-gray-600">
      <span className="tabular">
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} {t('of')} {total.toLocaleString(locale())}
      </span>
      <div className="flex gap-1">
        <Button variant="secondary" size="sm" icon={ChevronLeft} disabled={page <= 1} onClick={() => onPage(page - 1)}>
          {t('Prev')}
        </Button>
        <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          {t('Next')} <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

export function Modal({ open, title, onClose, children, footer, wide }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-8" onMouseDown={onClose}>
      <div
        className={cx('w-full rounded-xl bg-white shadow-xl', wide ? 'max-w-3xl' : 'max-w-lg')}
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3">
          <h3 className="font-semibold text-gray-900">{title}</h3>
          <button type="button" onClick={onClose} className="rounded p-1 text-gray-500 hover:bg-gray-100" aria-label={t('Close')}>
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3 px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-gray-100 px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-gray-200">
      {tabs.map((t) => {
        const v = typeof t === 'string' ? t : t.value
        const label = typeof t === 'string' ? humanize(t) : t.label
        return (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            className={cx(
              '-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium',
              value === v ? 'border-brand-600 text-brand-700' : 'border-transparent text-gray-500 hover:text-gray-800',
            )}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

/** KPI tile: label, big number, optional sub line. */
export function StatTile({ label, value, sub, tone }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-gray-200/80 bg-white px-4 py-3.5 shadow-sm shadow-slate-900/[0.03] transition-all hover:-translate-y-0.5 hover:shadow-md before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-brand-gradient">
      <div className="text-xs font-medium text-gray-500">{label}</div>
      <div className={cx('mt-1 text-2xl font-semibold tracking-tight', tone === 'alert' ? 'text-red-700' : 'text-gray-900')}>
        {value ?? '—'}
      </div>
      {sub && <div className="mt-0.5 text-xs text-gray-500">{sub}</div>}
    </div>
  )
}

export function DefinitionList({ items }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-3 border-b border-gray-100 py-1.5">
          <dt className="text-gray-500">{t(k)}</dt>
          <dd className="text-right font-medium text-gray-900">{v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ProgressBar({ pct, status }) {
  const width = Math.max(0, Math.min(100, pct || 0))
  const color = { achieved: 'bg-good', on_track: 'bg-good', at_risk: 'bg-warning', missed: 'bg-critical' }[status] || 'bg-brand-500'
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-full min-w-16 overflow-hidden rounded-full bg-gray-100">
        <div className={cx('h-full rounded-full', color)} style={{ width: `${width}%` }} />
      </div>
      <span className="tabular w-12 text-right text-xs text-gray-600">{pct ?? 0}%</span>
    </div>
  )
}
