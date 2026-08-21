import { useCallback, useEffect, useRef, useState } from 'react';

import { filesApi } from '@/api';
import {
  ArrowLeftIcon,
  AudioIcon,
  DownloadIcon,
  ExternalLinkIcon,
  FileIcon,
  FolderIcon,
  ImageIcon,
  SearchIcon,
  TrashIcon,
  VideoIcon,
  XIcon,
} from '@/components/Icons';
import { DropdownMenu } from '@/components/DropdownMenu';
import type { FileSearchResult } from '@/types';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function relativeTime(value: string): string {
  const date = new Date(value);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return 'now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}

const TYPE_FILTERS = [
  { key: '', label: 'All', Icon: undefined },
  { key: 'image', label: 'Images', Icon: ImageIcon },
  { key: 'video', label: 'Videos', Icon: VideoIcon },
  { key: 'audio', label: 'Audio', Icon: AudioIcon },
  { key: 'document', label: 'Docs', Icon: FileIcon },
] as const;

const SORT_OPTIONS = [
  { key: 'newest', label: 'Newest' },
  { key: 'oldest', label: 'Oldest' },
  { key: 'largest', label: 'Largest' },
  { key: 'smallest', label: 'Smallest' },
  { key: 'name', label: 'Name' },
] as const;

interface FilesViewProps {
  onBack: () => void;
  onGoToNote: (noteId: number) => void;
}

export function FilesView({ onBack, onGoToNote }: FilesViewProps) {
  const [files, setFiles] = useState<FileSearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [sort, setSort] = useState('newest');
  const [deleting, setDeleting] = useState<Set<number>>(new Set());
  const [lightbox, setLightbox] = useState<string | null>(null);
  const debounceRef = useRef<number | undefined>(undefined);

  const fetchFiles = useCallback(async (s: string, t: string, srt: string) => {
    setError('');
    try {
      const result = await filesApi.list({
        search: s || undefined,
        type: t || undefined,
        sort: srt,
      });
      setFiles(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load files');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    void fetchFiles('', '', 'newest');
  }, [fetchFiles]);

  // Debounced refetch on filter change
  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      setLoading(true);
      void fetchFiles(search, typeFilter, sort);
    }, 300);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [search, typeFilter, sort, fetchFiles]);

  async function handleDelete(file: FileSearchResult) {
    setDeleting((prev) => new Set(prev).add(file.id));
    try {
      await filesApi.delete(file.id);
      setFiles((prev) => prev.filter((f) => f.id !== file.id));
    } catch {
      // WS update will sync
    } finally {
      setDeleting((prev) => {
        const next = new Set(prev);
        next.delete(file.id);
        return next;
      });
    }
  }

  const isImage = (ct: string) => ct.startsWith('image/');
  const isVideo = (ct: string) => ct.startsWith('video/');
  const isAudio = (ct: string) => ct.startsWith('audio/');

  function getTypeIcon(ct: string, size: number) {
    if (isImage(ct)) return <ImageIcon size={size} />;
    if (isVideo(ct)) return <VideoIcon size={size} />;
    if (isAudio(ct)) return <AudioIcon size={size} />;
    return <FileIcon size={size} />;
  }

  return (
    <div className="files-view">
      {/* Header */}
      <div className="files-header">
        <button type="button" onClick={onBack} className="thread-back-btn" aria-label="Back to notes">
          <ArrowLeftIcon size={16} />
        </button>
        <div className="files-header-info">
          <FolderIcon size={14} className="files-header-icon" />
          <span className="files-header-title">Files</span>
          {!loading && <span className="files-header-count">{files.length}</span>}
        </div>
      </div>

      {/* Toolbar */}
      <div className="files-toolbar">
        <div className="files-toolbar-inner">
          {/* Search */}
          <div className="files-search search-bar">
            <SearchIcon size={13} className="search-icon" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search files…"
              aria-label="Search files"
            />
            {search && (
              <button type="button" onClick={() => setSearch('')} aria-label="Clear search" className="search-clear">
                <XIcon size={12} />
              </button>
            )}
          </div>

          {/* Filters row: type chips + sort */}
          <div className="files-filters-row">
            <div className="files-type-chips">
              {TYPE_FILTERS.map(({ key, label, Icon }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTypeFilter(typeFilter === key ? '' : key)}
                  className={`files-chip${typeFilter === key ? ' active' : ''}`}
                  aria-pressed={typeFilter === key}
                >
                  {Icon && <Icon size={11} />}
                  {label}
                </button>
              ))}
            </div>

            <DropdownMenu
              value={sort}
              options={SORT_OPTIONS}
              onChange={setSort}
              label="Sort by"
            />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="files-content">
        {error && <div className="error-banner">{error}</div>}

        {loading ? (
          <div className="loading-spinner">
            <div className="spinner" />
          </div>
        ) : files.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              {search || typeFilter ? <SearchIcon size={20} /> : <FolderIcon size={20} />}
            </div>
            <p className="empty-state-title">
              {search || typeFilter ? 'No files found' : 'No files yet'}
            </p>
            <p className="empty-state-sub">
              {search || typeFilter
                ? 'Try different search or filters'
                : 'Files you attach to notes will appear here'}
            </p>
          </div>
        ) : (
          <div className="files-grid">
            {files.map((file) => {
              const url = filesApi.url(file.url);
              const downloadUrl = `${url}?download=true`;
              const showThumb = isImage(file.content_type);
              const showVideoThumb = isVideo(file.content_type);

              return (
                <div key={file.id} className={`files-card${deleting.has(file.id) ? ' is-deleting' : ''}`}>
                  {/* Thumbnail area */}
                  <div
                    className={`files-card-thumb${showThumb || showVideoThumb ? ' has-preview' : ''}`}
                    onClick={showThumb ? () => setLightbox(url) : undefined}
                  >
                    {showThumb ? (
                      <img src={url} alt={file.filename} loading="lazy" />
                    ) : showVideoThumb ? (
                      <video src={url} preload="metadata" />
                    ) : (
                      <div className="files-card-icon-wrap">
                        {getTypeIcon(file.content_type, 24)}
                      </div>
                    )}
                  </div>

                  {/* Info */}
                  <div className="files-card-body">
                    <span className="files-card-name" title={file.filename}>{file.filename}</span>
                    <div className="files-card-meta">
                      <span>{formatSize(file.size_bytes)}</span>
                      <span>·</span>
                      <span>{relativeTime(file.created_at)}</span>
                    </div>
                    {file.parent_content && (
                      <p className="files-card-parent" title={file.parent_content}>
                        {file.parent_type === 'thread' ? '💬 ' : ''}
                        {file.parent_content}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="files-card-actions">
                    <button
                      type="button"
                      onClick={() => onGoToNote(file.parent_id)}
                      className="files-action-btn"
                      title="Go to note"
                      aria-label="Go to note"
                    >
                      <ExternalLinkIcon size={13} />
                    </button>
                    <a href={downloadUrl} className="files-action-btn" title="Download" aria-label="Download">
                      <DownloadIcon size={13} />
                    </a>
                    <button
                      type="button"
                      onClick={() => void handleDelete(file)}
                      disabled={deleting.has(file.id)}
                      className="files-action-btn danger"
                      title="Delete"
                      aria-label="Delete file"
                    >
                      <TrashIcon size={13} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Lightbox */}
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
          <img
            src={lightbox}
            alt="Preview"
            className="lightbox-image"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
