import { useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from 'd3-force'
import { Maximize2, Minus, Plus } from 'lucide-react'
import { ARTIFACTS, CONCEPTS, ENTITIES, LINKS, PROJECTS, PROJECT_COLOR, artifact, degree, fragment, relationFrom, where } from '../data/model'
import { DocBadge, ProjectDot } from '../components/bits'

type Kind = 'doc' | 'concept' | 'entity'
type N = SimulationNodeDatum & { id: string; kind: Kind; label: string; r: number; color: string; project?: string }
type E = { s: string; t: string; kind: 'authored' | 'semantic' | 'tag'; label?: string }
const W = 1000, H = 720

function layout(showConcepts: boolean, showEntities: boolean, showSemantic: boolean) {
  const nodes: N[] = ARTIFACTS.map(a => ({ id: a.id, kind: 'doc', label: a.short, r: 9 + degree(a.id) * 1.6, color: PROJECT_COLOR[a.project], project: a.project }))
  const edges: E[] = LINKS.filter(l => showSemantic || l.origin === 'authored').map(l => ({ s: l.source, t: l.target, kind: l.origin, label: l.type }))
  if (showConcepts) CONCEPTS.forEach(c => { nodes.push({ id: `c:${c.name}`, kind: 'concept', label: c.name, r: 4 + Math.sqrt(c.fragments) * 1.3, color: '#94a3b8' }); c.artifacts.forEach(a => edges.push({ s: a, t: `c:${c.name}`, kind: 'tag' })) })
  if (showEntities) ENTITIES.filter(e => e.kind !== 'project').forEach(e => { nodes.push({ id: `e:${e.name}`, kind: 'entity', label: e.name, r: 5, color: '#b45309' }); e.artifacts.forEach(a => edges.push({ s: a, t: `e:${e.name}`, kind: 'tag' })) })
  // projects pull towards their own corner, so the two projects read as regions joined by shared documents
  const anchor: Record<string, [number, number]> = { CEREBRO: [W * 0.3, H * 0.38], MealSenseAI: [W * 0.72, H * 0.58], Coursework: [W * 0.42, H * 0.72], Infrastructure: [W * 0.62, H * 0.25] }
  const sim = forceSimulation(nodes)
    .force('link', forceLink<N, { source: string; target: string; kind: string }>(edges.map(e => ({ source: e.s, target: e.t, kind: e.kind }))).id(d => d.id)
      .distance(l => (l.kind === 'tag' ? 90 : 170)).strength(l => (l.kind === 'tag' ? 0.12 : l.kind === 'semantic' ? 0.25 : 0.5)))
    .force('charge', forceManyBody<N>().strength(d => (d.kind === 'doc' ? -900 : -160)))
    .force('x', forceX<N>(d => (d.project ? anchor[d.project][0] : W / 2)).strength(d => (d.kind === 'doc' ? 0.08 : 0.02)))
    .force('y', forceY<N>(d => (d.project ? anchor[d.project][1] : H / 2)).strength(d => (d.kind === 'doc' ? 0.08 : 0.02)))
    .force('collide', forceCollide<N>(d => d.r + (d.kind === 'doc' ? 46 : 18)))
    .stop()
  for (let i = 0; i < 400; i++) sim.tick()
  // fit the settled layout to the canvas, leaving room for labels
  const xs = nodes.map(n => n.x!), ys = nodes.map(n => n.y!)
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const k = Math.min((W - 220) / (x1 - x0 || 1), (H - 110) / (y1 - y0 || 1))
  nodes.forEach(n => { n.x = 110 + (n.x! - x0) * k + ((W - 220) - (x1 - x0) * k) / 2; n.y = 45 + (n.y! - y0) * k + ((H - 110) - (y1 - y0) * k) / 2 })
  const pos = new Map(nodes.map(n => [n.id, n]))
  return { nodes, edges, pos }
}

export default function Connect() {
  const [sp, setSp] = useSearchParams()
  const sel = sp.get('focus')
  const [showConcepts, setShowConcepts] = useState(false)
  const [showEntities, setShowEntities] = useState(false)
  const [showSemantic, setShowSemantic] = useState(true)
  const [hidden, setHidden] = useState<string[]>([])
  const [hover, setHover] = useState<string | null>(null)
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const g = useMemo(() => layout(showConcepts, showEntities, showSemantic), [showConcepts, showEntities, showSemantic])

  const visible = (id: string) => { const n = g.pos.get(id)!; return !(n.project && hidden.includes(n.project)) }
  const active = hover ?? sel
  const near = new Set<string>(active ? [active, ...g.edges.filter(e => e.s === active || e.t === active).flatMap(e => [e.s, e.t])] : [])
  const dim = (id: string) => active != null && !near.has(id)
  const select = (id: string | null) => setSp(id ? { focus: id } : {})

  const scale = () => (svg.current ? W / svg.current.clientWidth : 1)
  const onDown = (e: React.PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false } }
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current; if (!d) return
    const dx = e.clientX - d.x, dy = e.clientY - d.y
    if (Math.abs(dx) + Math.abs(dy) > 4) { d.moved = true; (e.currentTarget as Element).setPointerCapture?.(e.pointerId) }
    if (d.moved) setView(v => ({ ...v, x: d.vx + dx * scale(), y: d.vy + dy * scale() }))
  }
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current; drag.current = null
    if (d && !d.moved) { const id = (e.target as Element).closest('[data-node]')?.getAttribute('data-node'); select(id ?? null) }
  }
  const zoom = (f: number) => setView(v => { const k = Math.min(3, Math.max(0.5, v.k * f)); return { k, x: W / 2 - (W / 2 - v.x) * (k / v.k), y: H / 2 - (H / 2 - v.y) * (k / v.k) } })

  const selDoc = sel && !sel.includes(':') ? artifact(sel) : null
  const selTag = sel && sel.includes(':') ? g.pos.get(sel) : null
  const tagDocs = selTag ? (selTag.kind === 'concept' ? CONCEPTS.find(c => `c:${c.name}` === sel)!.artifacts : ENTITIES.find(e => `e:${e.name}` === sel)!.artifacts) : []

  return (
    <div className="max-w-7xl">
      <p className="eyebrow">Connect</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">Knowledge graph</h1>
      <p className="mt-1 text-ink-muted">Documents linked by the relationships they state, by text similarity, and by the concepts they share. Tap a node to focus it.</p>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        {PROJECTS.map(p => { const off = hidden.includes(p); return (
          <button key={p} aria-pressed={!off} onClick={() => setHidden(h => off ? h.filter(x => x !== p) : [...h, p])} className={`chip ${off ? 'opacity-40 line-through' : ''}`}><ProjectDot project={p} />{p}</button>) })}
        <span className="mx-1 h-4 w-px bg-line" aria-hidden="true" />
        {([['Concepts', showConcepts, setShowConcepts], ['Entities', showEntities, setShowEntities], ['Similarity links', showSemantic, setShowSemantic]] as const).map(([l, v, set]) => (
          <label key={l} className="chip cursor-pointer"><input type="checkbox" className="accent-[#2a5d9f]" checked={v} onChange={e => set(e.target.checked)} />{l}</label>))}
      </div>

      <div className="mt-3 grid lg:grid-cols-[1fr_340px] gap-4">
        <div className="card relative overflow-hidden">
          <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className="w-full aspect-[25/18] lg:aspect-auto lg:h-[62vh] lg:min-h-[420px] touch-none select-none cursor-grab active:cursor-grabbing bg-surface-subtle/40"
            onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => { drag.current = null }}
            onWheel={e => zoom(e.deltaY < 0 ? 1.1 : 0.9)} role="img" aria-label="Knowledge graph of documents, concepts and entities">
            <defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#8a94a3" /></marker></defs>
            <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
              {g.edges.filter(e => visible(e.s) && visible(e.t)).map((e, i) => {
                const a = g.pos.get(e.s)!, b = g.pos.get(e.t)!
                const dx = b.x! - a.x!, dy = b.y! - a.y!, len = Math.hypot(dx, dy) || 1
                const x2 = b.x! - (dx / len) * (b.r + 3), y2 = b.y! - (dy / len) * (b.r + 3)
                const on = active != null && (e.s === active || e.t === active)
                const faded = active != null && !on
                return <g key={i} opacity={faded ? 0.12 : 1}>
                  <line x1={a.x} y1={a.y} x2={e.kind === 'authored' ? x2 : b.x} y2={e.kind === 'authored' ? y2 : b.y}
                    stroke={e.kind === 'tag' ? '#cbd2db' : on ? '#2a5d9f' : '#8a94a3'} strokeWidth={e.kind === 'tag' ? 0.8 : on ? 2.2 : 1.3}
                    strokeDasharray={e.kind === 'semantic' ? '5 4' : undefined} markerEnd={e.kind === 'authored' ? 'url(#arrow)' : undefined} />
                  {on && e.kind !== 'tag' && <text x={(a.x! + b.x!) / 2} y={(a.y! + b.y!) / 2 - 4} textAnchor="middle" fontSize={11} fill="#2a5d9f" paintOrder="stroke" stroke="#fff" strokeWidth={4}>{e.label}</text>}
                </g> })}
              {g.nodes.filter(n => visible(n.id)).map(n => {
                const isSel = n.id === sel
                return <g key={n.id} data-node={n.id} transform={`translate(${n.x},${n.y})`} opacity={dim(n.id) ? 0.18 : 1} className="cursor-pointer"
                  onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover(null)}>
                  {n.kind === 'doc' ? <circle r={n.r} fill={n.color} stroke={isSel ? '#14171c' : '#fff'} strokeWidth={isSel ? 3 : 2} />
                    : n.kind === 'concept' ? <rect x={-n.r} y={-n.r} width={n.r * 2} height={n.r * 2} rx={2} transform="rotate(45)" fill="#fff" stroke={isSel ? '#14171c' : n.color} strokeWidth={isSel ? 2.5 : 1.5} />
                    : <rect x={-n.r} y={-n.r} width={n.r * 2} height={n.r * 2} rx={1.5} fill="#fff" stroke={isSel ? '#14171c' : n.color} strokeWidth={isSel ? 2.5 : 1.5} />}
                  {(n.kind === 'doc' || n.id === active || (near.has(n.id) && !g.pos.get(active!)?.project) || view.k > 1.4) &&
                    <text y={n.r + (n.kind === 'doc' ? 14 : 12)} textAnchor="middle" fontSize={n.kind === 'doc' ? 12 : 10.5} fontWeight={n.kind === 'doc' ? 600 : 400}
                      fill={n.kind === 'doc' ? '#14171c' : '#5b6472'} paintOrder="stroke" stroke="#fff" strokeWidth={4} strokeLinejoin="round">
                      {n.label.length > 26 ? n.label.slice(0, 24) + '…' : n.label}</text>}
                </g> })}
            </g>
          </svg>
          <div className="absolute right-3 top-3 flex flex-col gap-1">
            <button className="btn-ghost p-2" onClick={() => zoom(1.25)} aria-label="Zoom in"><Plus className="size-4" /></button>
            <button className="btn-ghost p-2" onClick={() => zoom(0.8)} aria-label="Zoom out"><Minus className="size-4" /></button>
            <button className="btn-ghost p-2" onClick={() => setView({ x: 0, y: 0, k: 1 })} aria-label="Reset view"><Maximize2 className="size-4" /></button>
          </div>
          <div className="absolute left-3 bottom-3 rounded-md bg-surface/90 border border-line px-2.5 py-1.5 text-[11px] text-ink-muted flex flex-wrap gap-x-3 gap-y-1">
            <span className="flex items-center gap-1"><svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="#8a94a3" strokeWidth="1.5" /></svg>stated</span>
            <span className="flex items-center gap-1"><svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="#8a94a3" strokeWidth="1.5" strokeDasharray="4 3" /></svg>similar</span>
            {showConcepts && <span className="flex items-center gap-1"><svg width="10" height="10"><rect x="2" y="2" width="6" height="6" transform="rotate(45 5 5)" fill="#fff" stroke="#94a3b8" /></svg>concept</span>}
            {showEntities && <span className="flex items-center gap-1"><svg width="10" height="10"><rect x="1" y="1" width="8" height="8" fill="#fff" stroke="#b45309" /></svg>entity</span>}
          </div>
        </div>

        <aside className="card p-4 lg:max-h-[62vh] lg:overflow-y-auto">
          {selDoc ? <>
            <div className="flex items-start gap-3"><DocBadge type={selDoc.type} size="sm" /><div className="min-w-0"><div className="font-semibold leading-snug">{selDoc.title}</div>
              <div className="text-xs text-ink-subtle">{selDoc.kind} · {selDoc.project}</div></div></div>
            <p className="mt-2 text-sm text-ink-muted">{selDoc.summary}</p>
            <Link to={`/library/${selDoc.id}`} className="mt-2 inline-block text-sm text-accent hover:underline">Open document →</Link>
            <h3 className="mt-4 eyebrow">Connections</h3>
            <ul className="mt-2 space-y-2.5">{LINKS.filter(l => l.source === selDoc.id || l.target === selDoc.id).map((l, i) => {
              const r = relationFrom(l, selDoc.id), o = artifact(r.other), ev = l.evidence ? fragment(l.evidence) : null
              return <li key={i} className="text-sm">
                <button onClick={() => select(o.id)} className="text-left hover:text-accent"><span className="text-ink-muted">{r.label}</span> <span className="font-medium">{o.short}</span></button>
                {ev && <p className="mt-0.5 text-xs text-ink-subtle">“{ev.text}” <span className="whitespace-nowrap">({artifact(ev.artifact_id).short}, {where(ev)})</span></p>}
                {l.origin === 'semantic' && <p className="mt-0.5 text-xs text-ink-subtle">similarity score {(l.score ?? 0).toFixed(2)} · {l.shared?.join(', ')}</p>}
              </li> })}</ul>
          </> : selTag ? <>
            <div className="eyebrow">{selTag.kind}</div>
            <div className="mt-1 font-semibold">{selTag.label}</div>
            <p className="mt-1 text-sm text-ink-muted">Appears in {tagDocs.length} documents:</p>
            <ul className="mt-2 space-y-1.5">{tagDocs.map(id => { const a = artifact(id); return <li key={id}>
              <button onClick={() => select(id)} className="flex items-center gap-2 text-sm text-left hover:text-accent"><ProjectDot project={a.project} />{a.short}</button></li> })}</ul>
          </> : <>
            <h2 className="font-semibold">How to read this graph</h2>
            <ul className="mt-2 space-y-2 text-sm text-ink-muted list-disc pl-4">
              <li>Circles are documents, coloured by project and sized by how connected they are.</li>
              <li>Solid arrows are relationships a document states (for example “extends” or “evaluates”), each backed by a quoted sentence.</li>
              <li>Dashed lines join documents with similar wording that never mention each other.</li>
              <li>Turn on Concepts to add shared ideas as diamonds, or Entities for people, datasets and tools.</li>
              <li>The lecture notes, the Buddy runbook and the LLM plan bridge the two projects.</li>
            </ul>
            <p className="mt-3 text-xs text-ink-subtle">Try: <button className="text-accent hover:underline" onClick={() => select('ART-0003')}>CEREBRO Solution Architecture</button>, <button className="text-accent hover:underline" onClick={() => select('c:Grounding')}>Grounding</button>.</p>
          </>}
        </aside>
      </div>
    </div>
  )
}
