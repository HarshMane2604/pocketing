import { useState } from 'react';
import { filesApi } from '@/api';
import { DownloadIcon, FileIcon, TrashIcon, XIcon } from '@/components/Icons';
import type { Attachment } from '@/types';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface AttachmentPreviewProps {
  attachments: Attachment[];
  onDeleted?: (attachmentId: number) => void;
}

export function AttachmentPreview({ attachments, onDeleted }: AttachmentPreviewProps) {
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<number>>(new Set());

  if (!attachments || attachments.length === 0) return null;

  async function handleDelete(att: Attachment) {
    setDeleting((prev) => new Set(prev).add(att.id));
    try {
      await filesApi.delete(att.id);
      onDeleted?.(att.id);
    } catch {
      // silently fail — WS update will sync state
    } finally {
      setDeleting((prev) => {
        const next = new Set(prev);
        next.delete(att.id);
        return next;
      });
    }
  }

  const isImage = (ct: string) => ct.startsWith('image/');
  const isVideo = (ct: string) => ct.startsWith('video/');
  const isAudio = (ct: string) => ct.startsWith('audio/');

  return (
    <>
      <div className="attachment-grid">
        {attachments.map((att) => {
          const url = filesApi.url(att.url);
          const downloadUrl = `${url}?download=true`;

          if (isImage(att.content_type)) {
            return (
              <div key={att.id} className="attachment-item attachment-image">
                <img
                  src={url}
                  alt={att.filename}
                  loading="lazy"
                  onClick={() => setLightbox(url)}
                />
                <div className="attachment-overlay">
                  <span className="attachment-name" title={att.filename}>{att.filename}</span>
                  <div className="attachment-actions-mini">
                    <a href={downloadUrl} title="Download" className="att-action-btn">
                      <DownloadIcon size={12} />
                    </a>
                    {onDeleted && (
                      <button
                        type="button"
                        onClick={() => void handleDelete(att)}
                        disabled={deleting.has(att.id)}
                        title="Delete"
                        className="att-action-btn att-delete"
                      >
                        <TrashIcon size={12} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          }

          if (isVideo(att.content_type)) {
            return (
              <div key={att.id} className="attachment-item attachment-video">
                <video src={url} controls preload="metadata" />
                <div className="attachment-overlay">
                  <span className="attachment-name" title={att.filename}>{att.filename}</span>
                  <div className="attachment-actions-mini">
                    <a href={downloadUrl} title="Download" className="att-action-btn">
                      <DownloadIcon size={12} />
                    </a>
                    {onDeleted && (
                      <button
                        type="button"
                        onClick={() => void handleDelete(att)}
                        disabled={deleting.has(att.id)}
                        title="Delete"
                        className="att-action-btn att-delete"
                      >
                        <TrashIcon size={12} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          }

          if (isAudio(att.content_type)) {
            return (
              <div key={att.id} className="attachment-item attachment-audio">
                <audio src={url} controls preload="metadata" />
                <div className="attachment-overlay">
                  <span className="attachment-name" title={att.filename}>{att.filename}</span>
                  <div className="attachment-actions-mini">
                    <a href={downloadUrl} title="Download" className="att-action-btn">
                      <DownloadIcon size={12} />
                    </a>
                    {onDeleted && (
                      <button
                        type="button"
                        onClick={() => void handleDelete(att)}
                        disabled={deleting.has(att.id)}
                        title="Delete"
                        className="att-action-btn att-delete"
                      >
                        <TrashIcon size={12} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          }

          // Generic file card
          return (
            <div key={att.id} className="attachment-item attachment-file-card">
              <div className="file-card-icon">
                <FileIcon size={20} />
              </div>
              <div className="file-card-info">
                <span className="file-card-name" title={att.filename}>{att.filename}</span>
                <span className="file-card-size">{formatSize(att.size_bytes)}</span>
              </div>
              <div className="file-card-actions">
                <a href={downloadUrl} title="Download" className="att-action-btn">
                  <DownloadIcon size={13} />
                </a>
                {onDeleted && (
                  <button
                    type="button"
                    onClick={() => void handleDelete(att)}
                    disabled={deleting.has(att.id)}
                    title="Delete"
                    className="att-action-btn att-delete"
                  >
                    <TrashIcon size={13} />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Lightbox for images */}
      {lightbox && (
        <div className="lightbox-overlay" onClick={() => setLightbox(null)}>
          <button
            type="button"
            className="lightbox-close"
            onClick={() => setLightbox(null)}
            aria-label="Close"
          >
            <XIcon size={20} />
          </button>
          <img src={lightbox} alt="Preview" className="lightbox-image" onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </>
  );
}
