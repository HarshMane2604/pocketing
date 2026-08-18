import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { NoteRow } from './NoteRow';
import type { Note, NoteUpdate } from '@/types';

interface SortableNoteRowProps {
  note: Note;
  busy: boolean;
  onUpdate: (note: Note, update: NoteUpdate) => void;
  onDelete: (note: Note) => void;
  onOpenThread?: (note: Note) => void;
}

export function SortableNoteRow(props: SortableNoteRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: props.note.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.8 : 1,
    zIndex: isDragging ? 1 : 0,
    position: 'relative' as const,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <NoteRow {...props} dragHandleProps={{ ...attributes, ...listeners }} isDragging={isDragging} />
    </div>
  );
}
