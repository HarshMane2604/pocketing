import { useRef } from 'react';
import { PaperclipIcon, XIcon } from '@/components/Icons';

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB

interface FileUploadButtonProps {
  files: File[];
  onChange: (files: File[]) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileUploadButton({ files, onChange }: FileUploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  function addFiles(newFiles: FileList | File[]) {
    const incoming = Array.from(newFiles);
    const valid: File[] = [];
    for (const file of incoming) {
      if (file.size > MAX_FILE_SIZE) {
        alert(`"${file.name}" is too large (max 50 MB)`);
        continue;
      }
      if (file.size === 0) continue;
      // Avoid duplicates by name+size
      if (!files.some((f) => f.name === file.name && f.size === file.size)) {
        valid.push(file);
      }
    }
    if (valid.length > 0) {
      onChange([...files, ...valid]);
    }
  }

  function removeFile(index: number) {
    onChange(files.filter((_, i) => i !== index));
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        onChange={(e) => {
          if (e.target.files) addFiles(e.target.files);
          e.target.value = '';
        }}
        style={{ display: 'none' }}
        aria-label="Attach files"
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        className={`file-upload-btn${files.length > 0 ? ' has-files' : ''}`}
        title={files.length > 0 ? `${files.length} file${files.length > 1 ? 's' : ''} selected` : 'Attach files'}
        aria-label="Attach files"
      >
        <PaperclipIcon size={16} />
        {files.length > 0 && (
          <span className="file-upload-count">{files.length}</span>
        )}
      </button>

      {files.length > 0 && (
        <div className="selected-files">
          {files.map((file, i) => (
            <div key={`${file.name}-${file.size}-${i}`} className="selected-file-pill">
              <span className="selected-file-name" title={file.name}>
                {file.name}
              </span>
              <span className="selected-file-size">{formatSize(file.size)}</span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                className="selected-file-remove"
                aria-label={`Remove ${file.name}`}
              >
                <XIcon size={10} />
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
