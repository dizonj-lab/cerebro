import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, Info, Search } from 'lucide-react'
import { artifact, search, trail } from '../data/model'
import { DocBadge, Quote } from '../components/bits'
import { SUGGESTED } from './Dashboard'

/** Extractive recall: the answer is made of quoted passages, ranked by BM25, with the stated links between their sources. */
export default function Recall() {
  const [sp, setSp] = useSearchParams()
  const q = sp.get('q') ?? ''
  const [text, setText] = useState(q)
  useEffect(() => setText(q), [q])
  const hits = useMemo(() => search(q), [q])
  const top = hits.slice(0, 4)
  const sources = [...new Set(top.map(h => h.f.artifact_id))]
  const steps = trail([...new Set(hits.map(h => h.f.artifact_id))])
  const ask = (s: string) => setSp(s.trim() ? { q: s.trim() } : {})

  return (
    <div className="max-w-4xl">
      <p className="eyebrow">Recall</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">Ask your knowledge</h1>
      <form onSubmit={e => { e.preventDefault(); ask(text) }} className="mt-4 flex gap-2">
        <div className="relative flex-1"><Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />
          <input className="input pl-9" aria-label="Question" placeholder="Ask about your documents" value={text} onChange={e => setText(e.target.value)} /></div>
        <button className="btn-primary">Recall</button>
      </form>
      <div className="mt-3 flex flex-wrap gap-1.5">{SUGGESTED.map(s =>
        <button key={s} onClick={() => ask(s)} className={`chip hover:border-accent hover:text-accent ${s === q ? 'border-accent text-accent' : ''}`}>{s}</button>)}</div>

      {q && <div className="mt-6 space-y-5">
        {top.length === 0 ? <div className="card p-5 text-sm text-ink-muted">Nothing in your documents answers “{q}”. CEREBRO only answers from what it has learned, so it says so rather than guessing.</div> : <>
          <section className="card p-5">
            <div className="flex items-center justify-between gap-2"><h2 className="font-semibold">What your documents say</h2>
              <span className="chip">{sources.length} source{sources.length > 1 ? 's' : ''}</span></div>
            <div className="mt-4 space-y-4">{top.map(h => <Quote key={h.f.id} f={h.f} mark={h.terms} />)}</div>
            <p className="mt-4 flex gap-1.5 text-xs text-ink-subtle"><Info className="size-3.5 shrink-0 mt-px" />Extractive answer: every sentence is quoted from a source and ranked by keyword relevance (BM25). No language model is used in this demo, so nothing is paraphrased or invented.</p>
          </section>

          {steps.length > 0 && <section className="card p-5">
            <h2 className="font-semibold">Reasoning trail</h2>
            <p className="text-xs text-ink-muted">How the documents behind this answer refer to each other.</p>
            <ul className="mt-3 space-y-2">{steps.map((l, i) => {
              const s = artifact(l.source), t = artifact(l.target)
              return <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                <Link to={`/library/${s.id}`} className="font-medium hover:text-accent">{s.short}</Link>
                <span className="chip border-accent/30 bg-accent-subtle text-accent">{l.type}</span><ArrowRight className="size-3.5 text-ink-subtle" aria-hidden="true" />
                <Link to={`/library/${t.id}`} className="font-medium hover:text-accent">{t.short}</Link></li> })}</ul>
          </section>}

          <section>
            <h2 className="font-semibold text-sm">Sources</h2>
            <div className="mt-2 grid sm:grid-cols-2 gap-2">{sources.map(id => { const a = artifact(id); return (
              <Link key={id} to={`/library/${id}`} className="card p-3 flex items-center gap-3 min-w-0 hover:border-accent/50">
                <DocBadge type={a.type} size="sm" /><span className="min-w-0"><span className="block text-sm font-medium truncate">{a.title}</span><span className="text-xs text-ink-subtle">{a.kind} · {a.project}</span></span></Link>) })}</div>
          </section>
        </>}
      </div>}
    </div>
  )
}
