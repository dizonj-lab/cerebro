import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { ARTIFACTS, CONCEPTS, PROJECTS, degree, fmtDate } from '../data/model'
import { DocBadge, ProjectChip } from '../components/bits'

export default function Library() {
  const [q, setQ] = useState('')
  const [type, setType] = useState<'all' | 'pdf' | 'docx'>('all')
  const [project, setProject] = useState('all')
  const [concept, setConcept] = useState('all')
  const list = useMemo(() => ARTIFACTS.filter(a =>
    (type === 'all' || a.type === type) && (project === 'all' || a.project === project) && (concept === 'all' || a.concepts.includes(concept)) &&
    (!q || `${a.title} ${a.summary} ${a.kind}`.toLowerCase().includes(q.toLowerCase()))).sort((a, b) => b.date.localeCompare(a.date)), [q, type, project, concept])

  return (
    <div className="max-w-6xl">
      <p className="eyebrow">Learn</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">Library</h1>
      <p className="mt-1 text-ink-muted">Every artifact CEREBRO has learned, with its provenance and connections.</p>

      <div className="mt-5 grid gap-2 sm:grid-cols-[1fr_auto_auto_auto]">
        <div className="relative"><Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />
          <input className="input pl-9" placeholder="Filter by title or summary" aria-label="Filter documents" value={q} onChange={e => setQ(e.target.value)} /></div>
        <select className="input" aria-label="File type" value={type} onChange={e => setType(e.target.value as typeof type)}>
          <option value="all">All types</option><option value="pdf">PDF</option><option value="docx">Word</option></select>
        <select className="input" aria-label="Project" value={project} onChange={e => setProject(e.target.value)}>
          <option value="all">All projects</option>{PROJECTS.map(p => <option key={p}>{p}</option>)}</select>
        <select className="input" aria-label="Concept" value={concept} onChange={e => setConcept(e.target.value)}>
          <option value="all">All concepts</option>{CONCEPTS.map(c => <option key={c.name}>{c.name}</option>)}</select>
      </div>
      <p className="mt-3 text-xs text-ink-subtle">{list.length} of {ARTIFACTS.length} artifacts</p>

      <div className="mt-2 grid sm:grid-cols-2 xl:grid-cols-3 gap-3">{list.map(a => (
        <Link key={a.id} to={`/library/${a.id}`} className="card p-4 flex flex-col hover:border-accent/50 transition-colors">
          <div className="flex items-start gap-3">
            <DocBadge type={a.type} />
            <div className="min-w-0"><div className="font-medium leading-snug">{a.title}</div>
              <div className="mt-0.5 text-xs text-ink-subtle">{a.id} · {a.kind} · {fmtDate(a.date)}</div></div>
          </div>
          <p className="mt-3 text-sm text-ink-muted line-clamp-3 flex-1">{a.summary}</p>
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <ProjectChip project={a.project} />
            <span className="chip">{a.fragment_count} fragments</span>
            <span className="chip">{degree(a.id)} links</span>
          </div>
        </Link>))}</div>
      {!list.length && <p className="mt-8 text-center text-ink-muted">No artifacts match these filters.</p>}
    </div>
  )
}
