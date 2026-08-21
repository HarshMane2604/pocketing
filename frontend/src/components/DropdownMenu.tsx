import { useCallback, useEffect, useRef, useState } from 'react';

interface DropdownOption {
  key: string;
  label: string;
}

interface DropdownMenuProps {
  value: string;
  options: readonly DropdownOption[];
  onChange: (value: string) => void;
  label?: string;
  'aria-label'?: string;
}

export function DropdownMenu({ value, options, onChange, label, ...props }: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const selected = options.find((o) => o.key === value);

  const close = useCallback(() => setOpen(false), []);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        close();
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') close();
    }
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open, close]);

  function handleSelect(key: string) {
    onChange(key);
    close();
    triggerRef.current?.focus();
  }

  return (
    <div className="dropdown-menu" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`dropdown-trigger${open ? ' open' : ''}`}
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={props['aria-label']}
      >
        {label && <span className="dropdown-label">{label}</span>}
        <span className="dropdown-value">{selected?.label ?? value}</span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="dropdown-chevron"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div className="dropdown-popover" role="listbox">
          {options.map(({ key, label: optLabel }) => (
            <button
              key={key}
              type="button"
              role="option"
              aria-selected={key === value}
              className={`dropdown-item${key === value ? ' selected' : ''}`}
              onClick={() => handleSelect(key)}
            >
              <span className="dropdown-item-label">{optLabel}</span>
              {key === value && (
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="dropdown-item-check"
                  aria-hidden="true"
                >
                  <path d="m5 12 4 4L19 6" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
