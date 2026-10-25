import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Clock3, Library, MessageSquareText, Network, Search } from 'lucide-react'
import { ARTIFACTS, CONCEPTS, FRAGMENTS, LINKS, OWNER, artifact, degree, fmtDate } from '../data/model'
import { DocBadge, ProjectChip, Stat } from '../components/bits'

const PILLARS = [
  { name: 'Learn', to: '/library', icon: Library, text: 'Documents are inspected, enriched, reviewed and split into knowledge fragments with provenance.' },
  { name: 'Connect', to: '/connect', icon: Network, text: 'Explicit references and semantic similarity link documents, concepts and entities into a graph.' },
  { name: 'Reason', to: '/timeline', icon: Clock3, text: 'See how ideas evolved over time and which document built on which.' },
  { name: 'Recall', to: '/recall', icon: MessageSquareText, text: 'Ask a question; every sentence of the answer is quoted from a cited source.' },
]
export const SUGGESTED = ['Why is human review mandatory?', 'How is the knowledge pipeline evaluated?', 'Which datasets does MealSenseAI use?',
  'Where do both projects run?', 'How accurate is the food classifier?', 'Can the glucose estimate be used to adjust insulin?']

export default function Dashboard() {
  const [q, setQ] = useState('')
  const nav = useNavigate()
  const recent = [...ARTIFACTS].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5)
  const hubs = [...ARTIFACTS].sort((a, b) => degree(b.id) - degree(a.id)).slice(0, 5)
  const pdf = ARTIFACTS.filter(a => a.type === 'pdf').length
  const ask = (s: string) => s.trim() && nav(`/recall?q=${encodeURIComponent(s.trim())}`)

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <p className="eyebrow">The Construct</p>
        <h1 className="mt-1 text-2xl sm:text-3xl font-semibold tracking-tight">Welcome back, {OWNER.split(' ')[0]}</h1>
        <p className="mt-1 text-ink-muted">Your knowledge twin has learned {ARTIFACTS.length} documents and connected them {LINKS.length} ways.</p>
      </div>

      <form onSubmit={e => { e.preventDefault(); ask(q) }} className="card p-4">
        <label htmlFor="ask" className="text-sm font-medium">Ask your knowledge</label>
        <div className="mt-2 flex gap-2">
          <div className="relative flex-1"><Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />
            <input id="ask" className="input pl-9" placeholder="e.g. Why is human review mandatory?" value={q} onChange={e => setQ(e.target.value)} /></div>
          <button className="btn-primary">Recall</button>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">{SUGGESTED.slice(0, 4).map(s =>
          <button type="button" key={s} onClick={() => ask(s)} className="chip hover:border-accent hover:text-accent">{s}</button>)}</div>
      </form>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Artifacts" value={ARTIFACTS.length} sub={`${pdf} PDF · ${ARTIFACTS.length - pdf} Word`} />
        <Stat label="Knowledge fragments" value={FRAGMENTS.length} sub="each traceable to page or paragraph" />
        <Stat label="Relationships" value={LINKS.length} sub={`${LINKS.filter(l => l.origin === 'authored').length} stated · ${LINKS.filter(l => l.origin === 'semantic').length} semantic`} />
        <Stat label="Concepts" value={CONCEPTS.length} sub="across 4 projects" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <section className="card p-4 min-w-0">
          <h2 className="font-semibold">Recently learned</h2>
          <ul className="mt-3 divide-y divide-line">{recent.map(a => (
            <li key={a.id}><Link to={`/library/${a.id}`} className="flex items-center gap-3 py-2.5 hover:text-accent">
              <DocBadge type={a.type} size="sm" /><span className="flex-1 min-w-0"><span className="block truncate text-sm font-medium">{a.title}</span>
                <span className="text-xs text-ink-subtle">{a.kind} · {fmtDate(a.date)}</span></span><ProjectChip project={a.project} /></Link></li>))}</ul>
        </section>
        <section className="card p-4 min-w-0">
          <h2 className="font-semibold">Most connected</h2>
          <p className="text-xs text-ink-muted">Documents that the rest of your knowledge leans on.</p>
          <ul className="mt-3 space-y-2.5">{hubs.map(a => {
            const n = degree(a.id); const max = degree(hubs[0].id)
            return <li key={a.id}><Link to={`/connect?focus=${a.id}`} className="block group">
              <div className="flex justify-between text-sm"><span className="truncate group-hover:text-accent">{artifact(a.id).short}</span><span className="tabular-nums text-ink-muted">{n} links</span></div>
              <div className="mt-1 h-1.5 rounded-full bg-surface-sunken"><div className="h-full rounded-full bg-accent" style={{ width: `${(n / max) * 100}%` }} /></div></Link></li> })}</ul>
        </section>
      </div>

      <section>
        <h2 className="font-semibold">Learn · Connect · Reason · Recall</h2>
        <div className="mt-3 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">{PILLARS.map(({ name, to, icon: Icon, text }) => (
          <Link key={name} to={to} className="card p-4 group hover:border-accent/50">
            <Icon className="size-5 text-accent" aria-hidden="true" /><div className="mt-2 font-medium flex items-center gap-1">{name}<ArrowRight className="size-3.5 opacity-0 group-hover:opacity-100 transition-opacity" /></div>
            <p className="mt-1 text-sm text-ink-muted">{text}</p></Link>))}</div>
      </section>
    </div>
  )
}
