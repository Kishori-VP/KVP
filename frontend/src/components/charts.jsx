/**
 * Charts follow the data-viz reference palette (light mode):
 * categorical slots in fixed order, 2px lines, recessive grid, hover tooltips,
 * a legend for 2+ series, status colours always paired with a text label,
 * and a table view for every chart.
 */
import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { locale, t } from '../lib/i18n'
import { Table } from './ui'

export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
export const STATUS = { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' }
const INK2 = '#52514e'
const MUTED = '#898781'
const GRID = '#e1e0d9'
const AXIS = '#c3c2b7'

const axisProps = {
  tick: { fill: MUTED, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: AXIS },
}

function ChartTooltip({ active, payload, label, labelFormatter }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-black/10 bg-white px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-medium text-gray-900">{labelFormatter ? labelFormatter(label) : label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-gray-700">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color || p.payload?.fill }} />
          <span className="flex-1">{p.name}</span>
          <span className="tabular font-medium text-gray-900">{Number(p.value).toLocaleString(locale())}</span>
        </div>
      ))}
    </div>
  )
}

function ViewToggle({ table, setTable }) {
  return (
    <button type="button" onClick={() => setTable(!table)} className="text-xs text-brand-700 hover:underline">
      {table ? t('Show chart') : t('Show table')}
    </button>
  )
}

/** Change over time. series: [{key, label}] (max 4 recommended). */
export function TrendChart({ data, series, xKey = 'period', height = 260, xFormatter }) {
  const [table, setTable] = useState(false)
  if (!data?.length) return null
  return (
    <div>
      <div className="mb-1 flex justify-end">
        <ViewToggle table={table} setTable={setTable} />
      </div>
      {table ? (
        <Table
          rowKey={(r) => r[xKey]}
          columns={[{ key: xKey, label: t('Period') }, ...series.map((s) => ({ key: s.key, label: s.label, className: 'tabular text-right' }))]}
          rows={data}
        />
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} tickFormatter={xFormatter} minTickGap={16} />
            <YAxis {...axisProps} axisLine={false} allowDecimals={false} />
            <Tooltip content={<ChartTooltip labelFormatter={xFormatter} />} cursor={{ stroke: AXIS, strokeWidth: 1 }} />
            {series.length > 1 && <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: INK2 }} />}
            {series.map((s, i) => (
              <Line
                key={s.key}
                type="linear"
                dataKey={s.key}
                name={s.label}
                stroke={SERIES[i]}
                strokeWidth={2}
                dot={data.length <= 14 ? { r: 3, strokeWidth: 2, stroke: '#fcfcfb' } : false}
                activeDot={{ r: 5, strokeWidth: 2, stroke: '#fcfcfb' }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

/**
 * Magnitude by category (single series, horizontal bars).
 * items: [{label, value, color?}] — color only for status meaning; label is always shown.
 */
export function BarList({ items, height, valueLabel = t('Count') }) {
  const [table, setTable] = useState(false)
  if (!items?.length) return null
  const h = height || Math.max(120, items.length * 30 + 20)
  return (
    <div>
      <div className="mb-1 flex justify-end">
        <ViewToggle table={table} setTable={setTable} />
      </div>
      {table ? (
        <Table rowKey={(r) => r.label} columns={[{ key: 'label', label: t('Category') }, { key: 'value', label: valueLabel, className: 'tabular text-right' }]} rows={items} />
      ) : (
        <ResponsiveContainer width="100%" height={h}>
          <BarChart data={items} layout="vertical" margin={{ top: 0, right: 28, bottom: 0, left: 0 }} barCategoryGap={6}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" {...axisProps} allowDecimals={false} />
            <YAxis type="category" dataKey="label" {...axisProps} width={140} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(11,11,11,0.04)' }} />
            <Bar
              dataKey="value"
              name={valueLabel}
              radius={[0, 4, 4, 0]}
              maxBarSize={18}
              label={{ position: 'right', fill: INK2, fontSize: 11 }}
            >
              {items.map((it) => (
                <Cell key={it.label} fill={it.color || SERIES[0]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

/** Vertical grouped bars for comparing up to 3 measures across periods/categories. */
export function GroupedBars({ data, xKey, series, height = 260 }) {
  const [table, setTable] = useState(false)
  if (!data?.length) return null
  return (
    <div>
      <div className="mb-1 flex justify-end">
        <ViewToggle table={table} setTable={setTable} />
      </div>
      {table ? (
        <Table
          rowKey={(r) => r[xKey]}
          columns={[{ key: xKey, label: t('Period') }, ...series.map((s) => ({ key: s.key, label: s.label, className: 'tabular text-right' }))]}
          rows={data}
        />
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }} barGap={2}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} />
            <YAxis {...axisProps} axisLine={false} allowDecimals={false} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(11,11,11,0.04)' }} />
            <Legend wrapperStyle={{ fontSize: 12, color: INK2 }} />
            {series.map((s, i) => (
              <Bar key={s.key} dataKey={s.key} name={s.label} fill={SERIES[i]} radius={[4, 4, 0, 0]} maxBarSize={22} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
