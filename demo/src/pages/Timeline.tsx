import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ARTIFACTS, LINKS, PROJECTS, PROJECT_COLOR, artifact, fmtDate, relationFrom } from '../data/model'
import { DocBadge, ProjectDot } from '../components/bits'

const W = 1000, LANE = 92, TOP = 40, LEFT = 120, RIGHT = 30
const day = (d: string) => new Date(d + 'T00:00:00').getTime() / 864e5

export default function Timeline() {
  const nav = useNavigate()
  const [hover, setHover] = useState<string | null>(null)
  const t0 = Math.min(...ARTIFACTS.map(a => day(a.date))) - 6, t1 = Math.max(...ARTIFACTS.map(a => day(a.date))) + 6
  const x = (d: string) => LEFT + ((day(d) - t0) / (t1 - t0)) * (W - LEFT - RIGHT)
  const lane = (p: string) => TOP + PROJECTS.indexOf(p as typeof PROJECTS[number]) * LANE + LANE / 2
  // spread documents in the same lane that are close in time
  const pos = new Map<string, [number, number]>()
  PROJECTS.forEach(p => {
    const docs = ARTIFACTS.filter(a => a.project === p).sort((a, b) => a.date.localeCompare(b.date))
    docs.forEach((a, i) => { const prev = docs[i - 1]; const close = prev && x(a.date) - x(prev.date) < 34
      pos.set(a.id, [x(a.date), lane(p) + (close && pos.get(prev.id)![1] <= lane(p) ? 18 : close ? -18 : 0)]) })
  })
  const H = TOP + PROJECTS.length * LANE + 30
  const months = Array.from({ length: 6 }, (_, i) => new Date(2026, 5 + i, 1)).filter(m => m.getTime() / 864e5 >= t0 && m.getTime() / 864e5 <= t1)
  const authored = LINKS.filter(l => l.origin === 'authored')
  const sorted = [...ARTIFACTS].sort((a, b) => a.date.localeCompare(b.date))

  return (
    <div className="max-w-6xl">
      <p className="eyebrow">Reason</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">Timeline</h1>
      <p className="mt-1 text-ink-muted">How the knowledge grew: each arc joins a document to an earlier one it builds on.</p>

      <div className="mt-4 card p-2 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[760px] w-full" role="img" aria-label="Timeline of documents by project, with arcs for stated relationships">
          {PROJECTS.map((p, i) => <g key={p}>
            <rect x={0} y={TOP + i * LANE} width={W} height={LANE} fill={i % 2 ? '#ffffff' : '#f7f8fa'} />
            <circle cx={16} cy={lane(p)} r={4} fill={PROJECT_COLOR[p]} /><text x={26} y={lane(p) + 4} fontSize={12} fontWeight={600} fill="#14171c">{p}</text>
          </g>)}
          {months.map(m => { const d = m.toISOString().slice(0, 10); return <g key={d}>
            <line x1={x(d)} x2={x(d)} y1={TOP - 6} y2={H - 26} stroke="#e3e6eb" />
            <text x={x(d) + 4} y={TOP - 12} fontSize={11} fill="#636c7a">{m.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })}</text></g> })}
          {authored.map((l, i) => {
            const [x1, y1] = pos.get(l.source)!, [x2, y2] = pos.get(l.target)!
            const on = hover != null && (l.source === hover || l.target === hover)
            const lift = Math.min(70, 20 + Math.abs(x1 - x2) * 0.18)
            return <path key={i} d={`M${x1},${y1} Q${(x1 + x2) / 2},${Math.min(y1, y2) - lift} ${x2},${y2}`} fill="none"
              stroke={on ? '#2a5d9f' : '#9aa3b1'} strokeWidth={on ? 2 : 1} opacity={hover && !on ? 0.15 : 0.75} />
          })}
          {ARTIFACTS.map(a => { const [cx, cy] = pos.get(a.id)!; const on = hover === a.id; return (
            <g key={a.id} className="cursor-pointer" onClick={() => nav(`/library/${a.id}`)} onMouseEnter={() => setHover(a.id)} onMouseLeave={() => setHover(null)}>
              <circle cx={cx} cy={cy} r={on ? 9 : 7} fill={PROJECT_COLOR[a.project]} stroke="#fff" strokeWidth={2} />
              {on && <text x={cx} y={cy - 14} textAnchor="middle" fontSize={11.5} fontWeight={600} fill="#14171c" paintOrder="stroke" stroke="#fff" strokeWidth={4}>{a.short}</text>}
            </g>) })}
          <text x={W - RIGHT} y={H - 8} textAnchor="end" fontSize={10.5} fill="#636c7a">Hover a dot to see its links; click to open it</text>
        </svg>
      </div>

      <ol className="mt-6 relative border-l border-line ml-3 space-y-4">{sorted.map(a => {
        const builds = LINKS.filter(l => l.origin === 'authored' && l.source === a.id)
        return <li key={a.id} className="pl-5 relative" onMouseEnter={() => setHover(a.id)} onMouseLeave={() => setHover(null)}>
          <span className="absolute -left-[5px] top-2 size-2.5 rounded-full ring-2 ring-white" style={{ background: PROJECT_COLOR[a.project] }} aria-hidden="true" />
          <div className="text-xs text-ink-subtle">{fmtDate(a.date)}</div>
          <Link to={`/library/${a.id}`} className="mt-0.5 flex items-center gap-2 font-medium hover:text-accent"><DocBadge type={a.type} size="sm" />{a.title}</Link>
          {builds.length > 0 && <p className="mt-1 text-sm text-ink-muted">{builds.map((l, i) => { const r = relationFrom(l, a.id); return (
            <span key={i}>{i > 0 && ' · '}{r.label} <Link to={`/library/${r.other}`} className="text-ink hover:text-accent"><ProjectDot project={artifact(r.other).project} /> {artifact(r.other).short}</Link></span>) })}</p>}
        </li> })}</ol>
    </div>
  )
}
