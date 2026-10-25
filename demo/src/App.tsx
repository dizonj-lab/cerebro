import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Clock3, LayoutDashboard, Library as LibraryIcon, Menu, MessageSquareText, Network, X } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import ArtifactPage from './pages/Artifact'
import Connect from './pages/Connect'
import Timeline from './pages/Timeline'
import Recall from './pages/Recall'
import { OWNER } from './data/model'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, pillar: '' },
  { to: '/library', label: 'Library', icon: LibraryIcon, pillar: 'Learn' },
  { to: '/connect', label: 'Connect', icon: Network, pillar: 'Connect' },
  { to: '/timeline', label: 'Timeline', icon: Clock3, pillar: 'Reason' },
  { to: '/recall', label: 'Recall', icon: MessageSquareText, pillar: 'Recall' },
]

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <img src="./cerebro-mark.png" alt="" aria-hidden="true" className="size-8 object-contain" />
      <div className="leading-tight">
        <div className="text-[15px] font-semibold tracking-[0.18em]">CEREBRO</div>
        <div className="hidden sm:block text-[10.5px] text-ink-subtle">Adaptive Knowledge and Reasoning Digital Twin</div>
      </div>
    </div>
  )
}

export default function App() {
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => { setOpen(false); window.scrollTo(0, 0) }, [loc.pathname])
  const initials = OWNER.split(' ').map(w => w[0]).join('').slice(0, 2)

  const nav = (
    <nav aria-label="Main" className="p-3 space-y-0.5">
      {NAV.map(({ to, label, icon: Icon, pillar }) => (
        <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) =>
          `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${isActive ? 'bg-accent-subtle text-accent font-medium' : 'text-ink-muted hover:bg-surface-sunken hover:text-ink'}`}>
          <Icon className="size-4" aria-hidden="true" /><span className="flex-1">{label}</span>
          {pillar && <span className="text-[10px] uppercase tracking-wider text-ink-subtle">{pillar}</span>}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-30 h-14 border-b border-line bg-surface/95 backdrop-blur flex items-center gap-3 px-4">
        <button className="lg:hidden p-1.5 -ml-1.5 rounded-md hover:bg-surface-sunken" onClick={() => setOpen(o => !o)} aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open}>
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
        <Logo />
        <span className="ml-2 chip border-accent/30 bg-accent-subtle text-accent">Demo workspace</span>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden sm:block text-sm text-ink-muted">{OWNER}</span>
          <span className="size-8 rounded-full bg-accent-subtle text-accent grid place-items-center text-xs font-semibold" aria-hidden="true">{initials}</span>
        </div>
      </header>
      <div className="flex flex-1 min-h-0">
        <aside className="hidden lg:block w-60 shrink-0 border-r border-line bg-surface-subtle">
          <div className="sticky top-14">{nav}
            <p className="px-6 pt-4 text-[11px] leading-relaxed text-ink-subtle">Everything runs in your browser. The sixteen documents are illustrative samples.</p></div>
        </aside>
        {open && <div className="lg:hidden fixed inset-0 top-14 z-20 bg-ink/20" onClick={() => setOpen(false)}>
          <aside className="w-64 h-full bg-surface-subtle border-r border-line" onClick={e => e.stopPropagation()}>{nav}</aside></div>}
        <main className="flex-1 min-w-0 px-4 sm:px-6 lg:px-8 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/library" element={<Library />} />
            <Route path="/library/:id" element={<ArtifactPage />} />
            <Route path="/connect" element={<Connect />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/recall" element={<Recall />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
