import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { XIcon } from '@/components/Icons';

export interface MediaTarget {
  url: string;
  filename?: string;
  type: 'image' | 'video';
}

interface MediaPreviewModalProps {
  media: MediaTarget | null;
  onClose: () => void;
}

export function MediaPreviewModal({ media, onClose }: MediaPreviewModalProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const triggerRef = useRef<Element | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Focus restore & body scroll lock
  useEffect(() => {
    if (!media) return;

    triggerRef.current = document.activeElement;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Focus close button / modal
    containerRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);

    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener('keydown', handleKeyDown, true);

      if (videoRef.current) {
        videoRef.current.pause();
      }

      if (triggerRef.current && 'focus' in triggerRef.current) {
        (triggerRef.current as HTMLElement).focus();
      }
    };
  }, [media, onClose]);

  if (!media) return null;

  return createPortal(
    <div
      ref={containerRef}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label={media.filename || 'Media preview'}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 select-none outline-none animate-in fade-in-0 duration-150"
      onClick={onClose}
      onPointerDown={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.stopPropagation()} // Allow browser native context menu inside preview (Copy Image, Save Image As, Inspect)
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        aria-label="Close preview"
        title="Close (Esc)"
        className="fixed top-4 right-4 z-[101] flex h-10 w-10 items-center justify-center rounded-full bg-black/50 text-white/90 hover:bg-black/80 hover:text-white transition-colors cursor-pointer"
      >
        <XIcon size={20} />
      </button>

      <div
        className="relative max-w-[92vw] max-h-[92vh] flex items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        {media.type === 'image' ? (
          <img
            src={media.url}
            alt={media.filename || 'Preview'}
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl cursor-default"
          />
        ) : (
          <video
            ref={videoRef}
            src={media.url}
            controls
            autoPlay
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl cursor-default"
          />
        )}
      </div>
    </div>,
    document.body
  );
}
