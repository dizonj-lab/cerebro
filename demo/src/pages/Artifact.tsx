import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Download, ExternalLink, Eye, Network } from 'lucide-react'
import { ENTITIES, artifact, fmtDate, fragment, fragmentsOf, linksOf, relationFrom, where } from '../data/model'
import { DocBadge, ProjectChip, ProjectDot } from '../components/bits'

export default function ArtifactPage() {
  const { id = '' } = useParams()
  const [sp] = useSearchParams()
  const focus = sp.get('f')
  const [preview, setPreview] = useState(false)
  const a = artifact(id)
  useEffect(() => { if (focus) setTimeout(() => document.getElementById(focus)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50) }, [focus, id])
  useEffect(() => setPreview(false), [id])
  if (!a) return <p>Artifact not found. <Link className="text-accent" to="/library">Back to the library</Link></p>
  const links = linksOf(a.id)
  const frags = fragmentsOf(a.id)
  const ents = ENTITIES.filter(e => e.artifacts.includes(a.id))

  return (
    <div className="max-w-6xl">
      <Link to="/library" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-accent"><ArrowLeft className="size-4" />Library</Link>
      <div className="mt-3 flex flex-col sm:flex-row sm:items-start gap-4">
        <DocBadge type={a.type} />
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{a.title}</h1>
          <p className="mt-1 text-sm text-ink-muted">{a.id} · {a.kind} · {a.authors.join(', ')} · {fmtDate(a.date)} · {a.pages ? `${a.pages} page${a.pages > 1 ? 's' : ''}` : 'Word document'} · {(a.size_bytes / 1024).toFixed(0)} KB</p>
          <div className="mt-2 flex flex-wrap gap-1.5"><ProjectChip project={a.project} />{a.concepts.slice(0, 6).map(c => <span key={c} className="chip">{c}</span>)}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {a.type === 'pdf' && <button className="btn-ghost" onClick={() => setPreview(p => !p)}><Eye className="size-4" />{preview ? 'Hide preview' : 'Preview'}</button>}
          <a className="btn-ghost" href={a.file} target="_blank" rel="noopener" {...(a.type === 'docx' ? { download: '' } : {})}>
            {a.type === 'pdf' ? <><ExternalLink className="size-4" />Open PDF</> : <><Download className="size-4" />Download .docx</>}</a>
          <Link className="btn-primary" to={`/connect?focus=${a.id}`}><Network className="size-4" />Show in graph</Link>
        </div>
      </div>
      <p className="mt-4 text-[15px] leading-relaxed max-w-3xl">{a.summary}</p>
      {preview && <iframe title={`${a.title} preview`} src={a.file} className="mt-4 w-full h-[70vh] rounded-lg border border-line" />}

      <div className="mt-6 grid lg:grid-cols-[1fr_320px] gap-6">
        <div className="space-y-6 min-w-0">
          <section>
            <h2 className="font-semibold">Relationships <span className="text-ink-subtle font-normal">({links.length})</span></h2>
            <p className="text-xs text-ink-muted">Stated relationships quote the sentence that makes them; similar ones come from text similarity.</p>
            <ul className="mt-3 space-y-2">{links.map((l, i) => {
              const r = relationFrom(l, a.id); const o = artifact(r.other)
              const ev = l.evidence ? fragment(l.evidence) : null
              return (
                <li key={i} className="card p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className={`chip ${l.origin === 'semantic' ? 'border-dashed' : 'border-accent/30 bg-accent-subtle text-accent'}`}>{r.label}</span>
                    <Link to={`/library/${o.id}`} className="inline-flex items-center gap-1.5 font-medium hover:text-accent"><ProjectDot project={o.project} />{o.title}</Link>
                  </div>
                  {ev && <p className="mt-2 text-sm text-ink-muted border-l-2 border-line pl-3">“{ev.text}” <Link className="text-xs text-accent hover:underline whitespace-nowrap" to={`/library/${ev.artifact_id}?f=${ev.id}`}>{artifact(ev.artifact_id).short}, {where(ev)}</Link></p>}
                  {l.origin === 'semantic' && <p className="mt-2 text-xs text-ink-muted">TF-IDF similarity score {(l.score ?? 0).toFixed(2)}{l.shared?.length ? ` · shared concepts: ${l.shared.join(', ')}` : ''}</p>}
                </li>)})}</ul>
          </section>

          <section>
            <h2 className="font-semibold">Knowledge fragments <span className="text-ink-subtle font-normal">({frags.length})</span></h2>
            <ol className="mt-3 space-y-2">{frags.map(f => (
              <li key={f.id} id={f.id} className={`rounded-lg border p-3 scroll-mt-20 ${f.id === focus ? 'border-accent bg-accent-subtle/60' : 'border-line'}`}>
                <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-ink-subtle"><span className="font-mono">{f.id}</span><span>· {f.section}</span><span>· {where(f)}</span></div>
                <p className="mt-1 text-sm leading-relaxed">{f.text}</p>
                {(f.concepts.length > 0 || f.entities.length > 0) && <div className="mt-2 flex flex-wrap gap-1">
                  {f.concepts.map(c => <span key={c} className="chip">{c}</span>)}
                  {f.entities.map(e => <span key={e} className="chip border-accent/30 text-accent">{e}</span>)}</div>}
              </li>))}</ol>
          </section>
        </div>

        <aside className="space-y-4">
          <section className="card p-4">
            <h2 className="font-semibold text-sm">Provenance</h2>
            <ol className="mt-3 relative border-l border-line ml-2 space-y-3">{a.pipeline.map(s => (
              <li key={s.step} className="pl-4 relative">
                <CheckCircle2 className="size-4 text-success bg-surface absolute -left-2 top-0.5" aria-hidden="true" />
                <div className="text-sm font-medium">{s.step}</div>
                <div className="text-xs text-ink-muted break-words">{s.detail}</div>
                <div className="text-[11px] text-ink-subtle">{new Date(s.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
              </li>))}</ol>
          </section>
          {ents.length > 0 && <section className="card p-4">
            <h2 className="font-semibold text-sm">Entities</h2>
            <ul className="mt-2 space-y-1.5">{ents.map(e => <li key={e.name} className="flex justify-between text-sm"><span>{e.name}</span><span className="text-xs text-ink-subtle">{e.kind} · in {e.artifacts.length} docs</span></li>)}</ul>
          </section>}
          <section className="card p-4 text-xs text-ink-muted break-all"><div className="font-semibold text-sm text-ink mb-1">Integrity</div>SHA-256 {a.sha256}</section>
        </aside>
      </div>
    </div>
  )
}
