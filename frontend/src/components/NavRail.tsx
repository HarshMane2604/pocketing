import { FolderIcon, LinkIcon, NotesIcon, PauseIcon, PlusIcon } from '@/components/Icons';

export type View = 'notes' | 'links' | 'files' | 'onhold';

interface NavRailProps {
  view: View;
  onViewChange: (view: View) => void;
  onHoldCount?: number;
}

const NAV_ITEMS: { view: View; Icon: typeof NotesIcon; label: string }[] = [
  { view: 'notes', Icon: NotesIcon, label: 'Notes' },
  { view: 'links', Icon: LinkIcon, label: 'Links' },
  { view: 'files', Icon: FolderIcon, label: 'Files' },
  { view: 'onhold', Icon: PauseIcon, label: 'On Hold' },
];

export function NavRail({ view, onViewChange, onHoldCount = 0 }: NavRailProps) {
  return (
    <nav className="nav-rail" aria-label="Main navigation">
      <div className="nav-rail-items">
        {NAV_ITEMS.map(({ view: itemView, Icon, label }) => (
          <button
            key={itemView}
            type="button"
            className={`nav-rail-item${view === itemView ? ' active' : ''}`}
            onClick={() => onViewChange(itemView)}
            title={label}
            aria-label={label}
            aria-current={view === itemView ? 'page' : undefined}
          >
            <Icon size={18} />
            {itemView === 'onhold' && onHoldCount > 0 && (
              <span className="nav-rail-badge">
                {onHoldCount}
              </span>
            )}
          </button>
        ))}

        <div className="nav-rail-divider" />

        <button
          type="button"
          className="nav-rail-item disabled"
          disabled
          title="More sections coming soon"
          aria-label="Add section (coming soon)"
        >
          <PlusIcon size={16} />
        </button>
      </div>
    </nav>
  );
}
