import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis, LabelList,
} from 'recharts'
import { num } from '../format'

const AXIS = { fontSize: 11, fill: 'var(--text-muted)' }
const GRID = 'var(--gridline)'

/* Shared tooltip. Values wear text tokens; the series colour appears only as a
   small swatch beside the label, never as the text colour itself. */
function ChartTooltip({ active, payload, label, labelFormatter }) {
  if (!active || !payload?.length) return null
  return (
    <div className="tooltip">
      <div className="tooltip-title">{labelFormatter ? labelFormatter(label) : label}</div>
      {payload.map((p) => (
        <div className="tooltip-row" key={p.dataKey}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span className="legend-swatch" style={{ background: p.color, width: 8, height: 8 }} />
            {p.name}
          </span>
          <span>{num(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

export function Legend({ items }) {
  if (items.length < 2) return null
  return (
    <div className="legend">
      {items.map((i) => (
        <span className="legend-item" key={i.label}>
          <span className="legend-swatch" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  )
}

/** Vertical bars for a single measure over an ordered axis (years).
 *  One series, one colour -- bar length already encodes magnitude. */
export function TimeBars({ data, xKey, yKey, name, height = 210, color = 'var(--series-1)', onBarClick }) {
  if (!data?.length) return <div className="empty">No data for this selection</div>
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 14, right: 8, left: 0, bottom: 4 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--axis)' }} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={38} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
        <Bar
          dataKey={yKey} name={name} fill={color} radius={[4, 4, 0, 0]} maxBarSize={44}
          isAnimationActive={false}
          onClick={onBarClick ? (d) => onBarClick(d?.payload?.[xKey] ?? d?.[xKey]) : undefined}
          cursor={onBarClick ? 'pointer' : undefined}
        >
          <LabelList dataKey={yKey} position="top" fontSize={10.5} fill="var(--text-secondary)" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Horizontal bars for nominal categories ranked by magnitude.
 *  Single hue -- colouring by rank would double-encode bar length. */
export function RankedBars({
  data, labelKey, valueKey, name, height, color = 'var(--series-1)', onClick,
}) {
  if (!data?.length) return <div className="empty">No data for this selection</div>
  const h = height || Math.max(140, data.length * 27 + 26)
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 2, right: 40, left: 0, bottom: 2 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
        <YAxis
          type="category" dataKey={labelKey} tick={{ ...AXIS, fontSize: 11.5 }}
          tickLine={false} axisLine={false} width={196} interval={0}
          tickFormatter={(v) => (v?.length > 24 ? `${v.slice(0, 23)}…` : v)}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
        <Bar
          dataKey={valueKey} name={name} fill={color} radius={[0, 4, 4, 0]}
          maxBarSize={16} isAnimationActive={false}
          onClick={onClick} cursor={onClick ? 'pointer' : undefined}
        >
          <LabelList dataKey={valueKey} position="right" fontSize={11} fill="var(--text-secondary)" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Quartiles are ordered tiers, so they get the ordinal blue ramp rather than
 *  categorical hues -- Q1 most prominent, Q4 nearest the surface. Segments are
 *  separated by a 2px surface gap, never a border. */
export function QuartileStack({ data, xKey, height = 230 }) {
  if (!data?.length) return <div className="empty">No data for this selection</div>
  const keys = [
    { k: 'q1', label: 'Q1', color: 'var(--q1)' },
    { k: 'q2', label: 'Q2', color: 'var(--q2)' },
    { k: 'q3', label: 'Q3', color: 'var(--q3)' },
    { k: 'q4', label: 'Q4', color: 'var(--q4)' },
  ]
  return (
    <>
      <Legend items={keys.map((k) => ({ label: `${k.label} journals`, color: k.color }))} />
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--axis)' }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={38} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--surface-2)' }} />
          {keys.map((k, i) => (
            <Bar
              key={k.k} dataKey={k.k} name={k.label} stackId="q" fill={k.color}
              maxBarSize={46} stroke="var(--surface-1)" strokeWidth={2}
              isAnimationActive={false}
              radius={i === keys.length - 1 ? [4, 4, 0, 0] : 0}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </>
  )
}

/** Multi-series trend. Categorical hues in fixed slot order, each line direct-
 *  labelled at its endpoint so identity never rests on colour alone. */
export function MultiLine({ data, xKey, series, height = 240 }) {
  if (!data?.length || !series.length) return <div className="empty">No data for this selection</div>
  return (
    <>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} />
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 10, right: 54, left: 0, bottom: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--axis)' }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={38} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }} />
          {series.map((s) => (
            <Line
              key={s.key} type="monotone" dataKey={s.key} name={s.label}
              stroke={s.color} strokeWidth={2}
              dot={{ r: 3, fill: s.color, stroke: 'var(--surface-1)', strokeWidth: 2 }}
              activeDot={{ r: 5, stroke: 'var(--surface-1)', strokeWidth: 2 }}
              isAnimationActive={false}
            >
              <LabelList
                dataKey={s.key} position="right" fontSize={10.5} fill="var(--text-secondary)"
                formatter={(v, _e, i) => (i === data.length - 1 ? s.label : '')}
              />
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  )
}

/** Single-measure trend over time. One series, so no legend -- the card title
 *  names it -- with the final value direct-laballed at the endpoint. */
export function Trend({ data, xKey, yKey, name, height = 200, color = 'var(--series-1)' }) {
  if (!data?.length) return <div className="empty">No snapshots recorded yet</div>
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 12, right: 46, left: 0, bottom: 4 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--axis)' }} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={44} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }} />
        <Line
          type="monotone" dataKey={yKey} name={name} stroke={color} strokeWidth={2}
          dot={{ r: 3, fill: color, stroke: 'var(--surface-1)', strokeWidth: 2 }}
          activeDot={{ r: 5, stroke: 'var(--surface-1)', strokeWidth: 2 }}
          isAnimationActive={false}
        >
          <LabelList
            dataKey={yKey} position="right" fontSize={11} fill="var(--text-secondary)"
            formatter={(v, _e, i) => (i === data.length - 1 ? num(v) : '')}
          />
        </Line>
      </LineChart>
    </ResponsiveContainer>
  )
}

const DONUT_COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']

function DonutTooltip({ active, payload, total }) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  const pct = total ? ((p.value / total) * 100).toFixed(1) : '0.0'
  return (
    <div className="tooltip">
      <div className="tooltip-title">{p.name}</div>
      <div className="tooltip-row">
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span className="legend-swatch" style={{ background: p.payload.fill, width: 8, height: 8 }} />
          {num(p.value)}
        </span>
        <span>{pct}%</span>
      </div>
    </div>
  )
}

/** Part-to-whole for a true partition -- every record contributes to exactly
 *  one wedge, so the ring always reads as 100% (unlike campus or subject
 *  tallies, where one record counts toward several categories and a donut
 *  would misstate the total). Categorical hues in fixed slot order; a long
 *  tail folds into "Other" so the ring never exceeds four wedges plus the
 *  remainder. The hole carries the total, like a small hero figure -- no
 *  on-arc labels, since the legend + tooltip already carry identity and share. */
export function Donut({ data, labelKey, valueKey, height = 240, maxSlices = 4 }) {
  if (!data?.length) return <div className="empty">No data for this selection</div>
  const sorted = [...data].sort((a, b) => b[valueKey] - a[valueKey])
  const head = sorted.slice(0, maxSlices)
  const otherTotal = sorted.slice(maxSlices).reduce((s, r) => s + r[valueKey], 0)
  const slices = otherTotal > 0 ? [...head, { [labelKey]: 'Other', [valueKey]: otherTotal }] : head
  const total = slices.reduce((s, r) => s + r[valueKey], 0)
  const colorFor = (i) => (i < DONUT_COLORS.length ? DONUT_COLORS[i] : 'var(--q-unranked)')

  return (
    <>
      <Legend
        items={slices.map((s, i) => ({
          label: `${s[labelKey]} · ${((s[valueKey] / total) * 100).toFixed(0)}%`,
          color: colorFor(i),
        }))}
      />
      <div style={{ position: 'relative' }}>
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            <Tooltip content={<DonutTooltip total={total} />} />
            <Pie
              data={slices} dataKey={valueKey} nameKey={labelKey}
              innerRadius="62%" outerRadius="92%" paddingAngle={2} cornerRadius={4}
              stroke="var(--surface-1)" strokeWidth={2} isAnimationActive={false}
            >
              {slices.map((s, i) => <Cell key={s[labelKey]} fill={colorFor(i)} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div
          style={{
            position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
          }}
        >
          <div style={{ fontSize: 22, fontWeight: 640, letterSpacing: '-0.02em' }}>{num(total)}</div>
          <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Total
          </div>
        </div>
      </div>
    </>
  )
}

/** Quartile mix as one horizontal 100% bar -- part-to-whole at a glance for a
 *  single entity (a faculty member, a department). Labels only where they fit. */
export function QuartileBar({ counts }) {
  const order = ['Q1', 'Q2', 'Q3', 'Q4', 'Unranked']
  const colors = {
    Q1: 'var(--q1)', Q2: 'var(--q2)', Q3: 'var(--q3)',
    Q4: 'var(--q4)', Unranked: 'var(--q-unranked)',
  }
  const rows = order.map((k) => ({ k, v: counts[k] || 0 })).filter((r) => r.v > 0)
  const total = rows.reduce((s, r) => s + r.v, 0)
  if (!total) return <div className="empty">No journal-ranked publications</div>
  return (
    <>
      <div style={{ display: 'flex', gap: 2, height: 26, marginBottom: 8 }}>
        {rows.map((r) => {
          const share = (r.v / total) * 100
          return (
            <div
              key={r.k}
              title={`${r.k}: ${r.v} of ${total}`}
              style={{ width: `${share}%`, background: colors[r.k], borderRadius: 4 }}
            />
          )
        })}
      </div>
      <div className="legend">
        {rows.map((r) => (
          <span className="legend-item" key={r.k}>
            <span className="legend-swatch" style={{ background: colors[r.k] }} />
            {r.k} &middot; {r.v}
          </span>
        ))}
      </div>
    </>
  )
}
