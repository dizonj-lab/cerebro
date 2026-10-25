import { Link } from 'react-router-dom'
import { FileText, FileType2 } from 'lucide-react'
import { PROJECT_COLOR, artifact, where, type Fragment } from '../data/model'

export function DocBadge({ type, size = 'md' }: { type: 'pdf' | 'docx'; size?: 'sm' | 'md' }) {
  const pdf = type === 'pdf'
  const cls = size === 'sm' ? 'size-7 text-[9px]' : 'size-10 text-[10px]'
  return (
    <span aria-label={pdf ? 'PDF' : 'Word document'} className={`${cls} shrink-0 rounded-md grid place-items-center font-semibold ${pdf ? 'bg-[#fdecea] text-[#b42318]' : 'bg-accent-subtle text-accent'}`}>
      <span className="flex flex-col items-center leading-none gap-0.5">{pdf ? <FileText className="size-3.5" /> : <FileType2 className="size-3.5" />}{pdf ? 'PDF' : 'DOCX'}</span>
    </span>
  )
}

export const ProjectDot = ({ project }: { project: string }) =>
  <span className="inline-block size-2 rounded-full shrink-0" style={{ background: PROJECT_COLOR[project] }} aria-hidden="true" />

export const ProjectChip = ({ project }: { project: string }) =>
  <span className="chip"><ProjectDot project={project} />{project}</span>

/** A quoted passage with its source and location, linking to that spot in the document. */
export function Quote({ f, mark }: { f: Fragment; mark?: string[] }) {
  const a = artifact(f.artifact_id)
  let text: React.ReactNode = f.text
  if (mark?.length) {
    const re = new RegExp(`\\b((?:${mark.map(m => m.replace(/[^a-z0-9-]/g, '')).filter(Boolean).join('|')})[\\w-]*)`, 'gi')
    text = f.text.split(re).map((part, i) => i % 2 ? <mark key={i} className="bg-accent-subtle text-ink rounded-sm px-0.5">{part}</mark> : part)
  }
  return (
    <blockquote className="border-l-2 border-accent/40 pl-3">
      <p className="text-sm text-ink leading-relaxed">“{text}”</p>
      <Link to={`/library/${a.id}?f=${f.id}`} className="mt-1 inline-flex items-center gap-1.5 text-xs text-accent hover:underline">
        <DocBadge type={a.type} size="sm" /><span className="font-medium">{a.short}</span><span className="text-ink-subtle">· {f.section} · {where(f)}</span>
      </Link>
    </blockquote>
  )
}

export const Stat = ({ label, value, sub }: { label: string; value: string | number; sub?: string }) => (
  <div className="card p-4"><div className="eyebrow">{label}</div><div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>{sub && <div className="text-xs text-ink-muted mt-0.5">{sub}</div>}</div>
)
