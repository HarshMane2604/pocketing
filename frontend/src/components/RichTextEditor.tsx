import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { Editor, JSONContent } from '@tiptap/core';
import { EditorContent, useEditor } from '@tiptap/react';
import { BubbleMenu } from '@tiptap/react/menus';
import type { EmojiStyle, Theme } from 'emoji-picker-react';

import { SmileIcon } from '@/components/Icons';
import {
  documentIsEmpty,
  normalizeRichTextDocument,
  plainTextToDocument,
  richTextToPlainText,
  richTextEditorExtensions,
} from '@/components/richTextExtensions';
import { sanitizeRichTextHtml } from '@/components/richTextSanitize';

const EmojiPicker = lazy(() => import('emoji-picker-react'));

export interface RichTextChange {
  document: JSONContent;
  plainText: string;
  isEmpty: boolean;
}

interface RichTextEditorProps {
  document: JSONContent | null;
  plainText: string;
  onChange: (value: RichTextChange) => void;
  placeholder: string;
  ariaLabel: string;
  autoFocus?: boolean;
  maxLength?: number;
  className?: string;
  footer?: ReactNode;
  onSubmit?: (value: RichTextChange) => void;
  onCancel?: () => void;
  onBlur?: () => void;
}

interface SlashState {
  query: string;
  from: number;
  to: number;
  left: number;
  top: number;
}

interface SlashCommand {
  id: string;
  label: string;
  keywords: string;
  icon: string;
  run: (editor: Editor) => void;
}

type ToolbarButtonProps = {
  label: string;
  title?: string;
  active?: boolean;
  disabled?: boolean;
  children: ReactNode;
  onClick: () => void;
};

function ToolbarButton({ label, title, active = false, disabled = false, children, onClick }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      className={`rich-toolbar-btn${active ? ' is-active' : ''}`}
      aria-label={label}
      aria-pressed={active}
      title={title ?? label}
      disabled={disabled}
      onPointerDown={(event) => event.preventDefault()}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function normalizeLink(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const href = /^[a-z][a-z\d+.-]*:/i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    const url = new URL(href);
    return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? href : null;
  } catch {
    return null;
  }
}

function editorPlainText(editor: Editor): string {
  return richTextToPlainText(normalizeRichTextDocument(editor.getJSON()));
}

function readEditorValue(editor: Editor): RichTextChange {
  const nextDocument = normalizeRichTextDocument(editor.getJSON());
  return {
    document: nextDocument,
    plainText: editorPlainText(editor),
    isEmpty: documentIsEmpty(nextDocument),
  };
}

export function RichTextEditor({
  document: richDocument,
  plainText,
  onChange,
  placeholder,
  ariaLabel,
  autoFocus = false,
  maxLength = 4000,
  className = '',
  footer,
  onSubmit,
  onCancel,
  onBlur,
}: RichTextEditorProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const slashRef = useRef<SlashState | null>(null);
  const slashIndexRef = useRef(0);
  const onSubmitRef = useRef(onSubmit);
  const onCancelRef = useRef(onCancel);
  const onChangeRef = useRef(onChange);
  const lastDocumentRef = useRef('');
  const [toolbarOpen, setToolbarOpen] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkValue, setLinkValue] = useState('');
  const [linkError, setLinkError] = useState('');
  const [slash, setSlash] = useState<SlashState | null>(null);
  const [slashIndex, setSlashIndex] = useState(0);

  useEffect(() => { onSubmitRef.current = onSubmit; }, [onSubmit]);
  useEffect(() => { onCancelRef.current = onCancel; }, [onCancel]);
  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);
  useEffect(() => { slashRef.current = slash; }, [slash]);
  useEffect(() => { slashIndexRef.current = slashIndex; }, [slashIndex]);

  const commands = useMemo<SlashCommand[]>(() => [
    { id: 'heading-1', label: 'Heading 1', keywords: 'heading h1 title', icon: 'H1', run: (e) => e.chain().focus().setHeading({ level: 1 }).run() },
    { id: 'heading-2', label: 'Heading 2', keywords: 'heading h2 subtitle', icon: 'H2', run: (e) => e.chain().focus().setHeading({ level: 2 }).run() },
    { id: 'heading-3', label: 'Heading 3', keywords: 'heading h3', icon: 'H3', run: (e) => e.chain().focus().setHeading({ level: 3 }).run() },
    { id: 'bullet', label: 'Bulleted list', keywords: 'bullet unordered list', icon: '•', run: (e) => e.chain().focus().toggleBulletList().run() },
    { id: 'numbered', label: 'Numbered list', keywords: 'number ordered list', icon: '1.', run: (e) => e.chain().focus().toggleOrderedList().run() },
    { id: 'todo', label: 'To-do list', keywords: 'todo task checklist checkbox', icon: '☑', run: (e) => e.chain().focus().toggleTaskList().run() },
    { id: 'quote', label: 'Blockquote', keywords: 'quote citation', icon: '“', run: (e) => e.chain().focus().toggleBlockquote().run() },
    { id: 'code', label: 'Code block', keywords: 'code pre developer', icon: '</>', run: (e) => e.chain().focus().toggleCodeBlock().run() },
    { id: 'divider', label: 'Divider', keywords: 'divider horizontal rule separator', icon: '—', run: (e) => e.chain().focus().setHorizontalRule().run() },
    { id: 'link', label: 'Link', keywords: 'link url website', icon: '↗', run: () => setLinkOpen(true) },
  ], []);

  const filteredCommands = useMemo(() => {
    const query = slash?.query.trim().toLowerCase() ?? '';
    return commands.filter((command) => `${command.label} ${command.keywords}`.toLowerCase().includes(query));
  }, [commands, slash?.query]);

  const updateSlashMenu = useCallback((editor: Editor) => {
    const { state, view } = editor;
    const { $from } = state.selection;
    if (!state.selection.empty || !$from.parent.isTextblock) {
      setSlash(null);
      return;
    }
    const textBefore = $from.parent.textBetween(0, $from.parentOffset, undefined, '\ufffc');
    const match = textBefore.match(/(?:^|\s)\/([a-z\d-]*)$/i);
    if (!match) {
      setSlash(null);
      return;
    }
    const query = match[1];
    const from = state.selection.from - query.length - 1;
    const rootRect = rootRef.current?.getBoundingClientRect();
    const coords = view.coordsAtPos(state.selection.from);
    const next = {
      query,
      from,
      to: state.selection.from,
      left: Math.max(8, Math.min((coords.left - (rootRect?.left ?? 0)), (rootRect?.width ?? 320) - 250)),
      top: coords.bottom - (rootRect?.top ?? 0) + 6,
    };
    setSlash(next);
    setSlashIndex(0);
  }, []);

  const emitChange = useCallback((editor: Editor) => {
    const nextValue = readEditorValue(editor);
    lastDocumentRef.current = JSON.stringify(editor.getJSON());
    onChangeRef.current(nextValue);
    updateSlashMenu(editor);
  }, [updateSlashMenu]);

  const runSlashCommand = useCallback((editor: Editor, command: SlashCommand) => {
    const activeSlash = slashRef.current;
    if (!activeSlash) return;
    editor.chain().focus().deleteRange({ from: activeSlash.from, to: activeSlash.to }).run();
    setSlash(null);
    command.run(editor);
  }, []);

  const editor = useEditor({
    extensions: richTextEditorExtensions(placeholder, maxLength),
    content: normalizeRichTextDocument(richDocument ?? plainTextToDocument(plainText)),
    autofocus: autoFocus ? 'end' : false,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        role: 'textbox',
        'aria-label': ariaLabel,
        'aria-multiline': 'true',
        class: 'rich-editor-prosemirror',
      },
      transformPastedHTML: sanitizeRichTextHtml,
      transformPastedText: (text) => text.replace(/\r\n/g, '\n'),
      handleKeyDown: (_view, event) => {
        const activeSlash = slashRef.current;
        if (activeSlash) {
          const query = activeSlash.query.toLowerCase();
          const available = commands.filter((command) => `${command.label} ${command.keywords}`.toLowerCase().includes(query));
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const direction = event.key === 'ArrowDown' ? 1 : -1;
            const next = (slashIndexRef.current + direction + available.length) % Math.max(available.length, 1);
            setSlashIndex(next);
            return true;
          }
          if (event.key === 'Enter' && available.length) {
            event.preventDefault();
            runSlashCommand(editor!, available[slashIndexRef.current] ?? available[0]);
            return true;
          }
          if (event.key === 'Escape') {
            event.preventDefault();
            setSlash(null);
            return true;
          }
        }

        const commandKey = event.ctrlKey || event.metaKey;
        if (commandKey && event.key.toLowerCase() === 'k') {
          event.preventDefault();
          setLinkValue(editor?.getAttributes('link').href ?? '');
          setLinkError('');
          setLinkOpen(true);
          return true;
        }
        if (commandKey && event.key === 'Enter' && onSubmitRef.current) {
          event.preventDefault();
          onSubmitRef.current(readEditorValue(editor!));
          return true;
        }
        if (event.key === 'Escape' && onCancelRef.current) {
          event.preventDefault();
          onCancelRef.current();
          return true;
        }
        if (event.key === 'Enter' && event.shiftKey) {
          event.preventDefault();
          editor?.chain().focus().splitBlock().run();
          return true;
        }
        if (event.key === 'Enter' && !event.shiftKey && editor) {
          const needsStructuralEnter = editor.isActive('bulletList')
            || editor.isActive('orderedList')
            || editor.isActive('taskList')
            || editor.isActive('codeBlock');
          if (!needsStructuralEnter && onSubmitRef.current) {
            event.preventDefault();
            onSubmitRef.current(readEditorValue(editor));
            return true;
          }
        }
        return false;
      },
    },
    onUpdate: ({ editor: activeEditor }) => emitChange(activeEditor),
    onSelectionUpdate: ({ editor: activeEditor }) => updateSlashMenu(activeEditor),
  }, []);

  useEffect(() => {
    if (!editor) return;
    const nextContent = normalizeRichTextDocument(richDocument ?? plainTextToDocument(plainText));
    const serialized = JSON.stringify(nextContent);
    if (serialized !== lastDocumentRef.current && serialized !== JSON.stringify(editor.getJSON())) {
      editor.commands.setContent(nextContent, { emitUpdate: false });
    }
    lastDocumentRef.current = serialized;
  }, [richDocument, editor, plainText]);

  useEffect(() => {
    if (!emojiOpen && !linkOpen) return;
    const handleDocumentKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        setEmojiOpen(false);
        setLinkOpen(false);
        setLinkError('');
        editor?.commands.focus();
      }
    };
    document.addEventListener('keydown', handleDocumentKey);
    return () => document.removeEventListener('keydown', handleDocumentKey);
  }, [editor, emojiOpen, linkOpen]);

  if (!editor) return null;

  const openLinkEditor = () => {
    setLinkValue(editor.getAttributes('link').href ?? '');
    setLinkError('');
    setEmojiOpen(false);
    setLinkOpen(true);
  };

  const applyLink = () => {
    if (!linkValue.trim()) {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
      setLinkOpen(false);
      return;
    }
    const href = normalizeLink(linkValue);
    if (!href) {
      setLinkError('Use an http, https, or email link.');
      return;
    }
    if (editor.state.selection.empty) {
      editor.chain().focus().insertContent({
        type: 'text',
        text: href.replace(/^mailto:/i, ''),
        marks: [{ type: 'link', attrs: { href } }],
      }).run();
    } else {
      editor.chain().focus().extendMarkRange('link').setLink({ href }).run();
    }
    setLinkOpen(false);
    setLinkError('');
  };

  const blockValue = editor.isActive('heading', { level: 1 }) ? 'h1'
    : editor.isActive('heading', { level: 2 }) ? 'h2'
      : editor.isActive('heading', { level: 3 }) ? 'h3'
        : 'paragraph';

  function handleBlur() {
    window.requestAnimationFrame(() => {
      if (rootRef.current?.contains(globalThis.document.activeElement)) return;
      setEmojiOpen(false);
      setLinkOpen(false);
      setSlash(null);
      onBlur?.();
    });
  }

  return (
    <div
      ref={rootRef}
      className={`rich-editor${toolbarOpen ? ' has-toolbar' : ''}${footer ? ' has-footer' : ''} ${className}`.trim()}
      onBlur={handleBlur}
      onPointerDown={(event) => event.stopPropagation()}
    >
      {toolbarOpen && (
        <div className="rich-toolbar" role="toolbar" aria-label="Text formatting">
          <div className="rich-toolbar-group">
            <ToolbarButton label="Bold" title="Bold (Ctrl/Cmd+B)" active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()}><strong>B</strong></ToolbarButton>
            <ToolbarButton label="Italic" title="Italic (Ctrl/Cmd+I)" active={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()}><em>I</em></ToolbarButton>
            <ToolbarButton label="Underline" title="Underline (Ctrl/Cmd+U)" active={editor.isActive('underline')} onClick={() => editor.chain().focus().toggleUnderline().run()}><u>U</u></ToolbarButton>
            <ToolbarButton label="Strikethrough" active={editor.isActive('strike')} onClick={() => editor.chain().focus().toggleStrike().run()}><s>S</s></ToolbarButton>
            <ToolbarButton label="Inline code" active={editor.isActive('code')} onClick={() => editor.chain().focus().toggleCode().run()}><span className="toolbar-code">&lt;/&gt;</span></ToolbarButton>
          </div>
          <span className="rich-toolbar-divider" />
          <select
            className="rich-toolbar-select"
            value={blockValue}
            aria-label="Text style"
            title="Text style"
            onChange={(event) => {
              const value = event.target.value;
              if (value === 'paragraph') editor.chain().focus().setParagraph().run();
              else editor.chain().focus().setHeading({ level: Number(value.slice(1)) as 1 | 2 | 3 }).run();
            }}
          >
            <option value="paragraph">Text</option>
            <option value="h1">H1</option>
            <option value="h2">H2</option>
            <option value="h3">H3</option>
          </select>
          <span className="rich-toolbar-divider" />
          <div className="rich-toolbar-group">
            <ToolbarButton label="Bulleted list" active={editor.isActive('bulletList')} onClick={() => editor.chain().focus().toggleBulletList().run()}>•</ToolbarButton>
            <ToolbarButton label="Numbered list" active={editor.isActive('orderedList')} onClick={() => editor.chain().focus().toggleOrderedList().run()}>1.</ToolbarButton>
            <ToolbarButton label="Checklist" active={editor.isActive('taskList')} onClick={() => editor.chain().focus().toggleTaskList().run()}>☑</ToolbarButton>
            <ToolbarButton label="Blockquote" active={editor.isActive('blockquote')} onClick={() => editor.chain().focus().toggleBlockquote().run()}>“</ToolbarButton>
            <ToolbarButton label="Code block" active={editor.isActive('codeBlock')} onClick={() => editor.chain().focus().toggleCodeBlock().run()}><span className="toolbar-code">[ ]</span></ToolbarButton>
            <ToolbarButton label="Horizontal divider" onClick={() => editor.chain().focus().setHorizontalRule().run()}>—</ToolbarButton>
          </div>
          <span className="rich-toolbar-divider" />
          <div className="rich-toolbar-group">
            <ToolbarButton label="Add link" title="Link (Ctrl/Cmd+K)" active={editor.isActive('link')} onClick={openLinkEditor}>↗</ToolbarButton>
            <ToolbarButton label="Align left" active={editor.isActive({ textAlign: 'left' })} onClick={() => editor.chain().focus().setTextAlign('left').run()}><span className="align-icon align-left"><i /><i /><i /></span></ToolbarButton>
            <ToolbarButton label="Align center" active={editor.isActive({ textAlign: 'center' })} onClick={() => editor.chain().focus().setTextAlign('center').run()}><span className="align-icon align-center"><i /><i /><i /></span></ToolbarButton>
            <ToolbarButton label="Align right" active={editor.isActive({ textAlign: 'right' })} onClick={() => editor.chain().focus().setTextAlign('right').run()}><span className="align-icon align-right"><i /><i /><i /></span></ToolbarButton>
            <ToolbarButton label="Undo" disabled={!editor.can().undo()} onClick={() => editor.chain().focus().undo().run()}>↶</ToolbarButton>
            <ToolbarButton label="Redo" disabled={!editor.can().redo()} onClick={() => editor.chain().focus().redo().run()}>↷</ToolbarButton>
          </div>
        </div>
      )}

      <div className="rich-editor-surface">
        <EditorContent editor={editor} />
        <div className="rich-editor-inline-actions">
          <button
            type="button"
            className={`editor-mode-btn${toolbarOpen ? ' is-active' : ''}`}
            aria-label={toolbarOpen ? 'Hide text formatting' : 'Enable text formatting'}
            aria-pressed={toolbarOpen}
            title="Text formatting"
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => {
              setToolbarOpen((open) => !open);
              setEmojiOpen(false);
              setLinkOpen(false);
              editor.commands.focus();
            }}
          >A</button>
          <button
            type="button"
            className={`editor-mode-btn editor-emoji-btn${emojiOpen ? ' is-active' : ''}`}
            aria-label="Add emoji"
            aria-pressed={emojiOpen}
            title="Add emoji"
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => {
              setEmojiOpen((open) => !open);
              setLinkOpen(false);
            }}
          >
            <SmileIcon size={16} />
          </button>
        </div>
      </div>

      <BubbleMenu editor={editor} options={{ placement: 'top' }}>
        <div className="rich-bubble-menu" role="toolbar" aria-label="Selection formatting">
          <ToolbarButton label="Bold" active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()}><strong>B</strong></ToolbarButton>
          <ToolbarButton label="Italic" active={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()}><em>I</em></ToolbarButton>
          <ToolbarButton label="Underline" active={editor.isActive('underline')} onClick={() => editor.chain().focus().toggleUnderline().run()}><u>U</u></ToolbarButton>
          <ToolbarButton label="Strikethrough" active={editor.isActive('strike')} onClick={() => editor.chain().focus().toggleStrike().run()}><s>S</s></ToolbarButton>
          <ToolbarButton label="Inline code" active={editor.isActive('code')} onClick={() => editor.chain().focus().toggleCode().run()}>&lt;/&gt;</ToolbarButton>
          <ToolbarButton label="Add link" active={editor.isActive('link')} onClick={openLinkEditor}>↗</ToolbarButton>
        </div>
      </BubbleMenu>

      {slash && (
        <div className="slash-menu" style={{ left: slash.left, top: slash.top }} role="listbox" aria-label="Insert block">
          {filteredCommands.length ? filteredCommands.map((command, index) => (
            <button
              key={command.id}
              type="button"
              role="option"
              aria-selected={index === slashIndex}
              className={`slash-command${index === slashIndex ? ' is-selected' : ''}`}
              onPointerDown={(event) => event.preventDefault()}
              onMouseEnter={() => setSlashIndex(index)}
              onClick={() => runSlashCommand(editor, command)}
            >
              <span className="slash-command-icon">{command.icon}</span>
              <span>{command.label}</span>
            </button>
          )) : <div className="slash-empty">No matching commands</div>}
        </div>
      )}

      {linkOpen && (
        <div className="link-popover" role="dialog" aria-label="Edit link">
          <label htmlFor={`link-${ariaLabel.replace(/\s/g, '-')}`}>Link</label>
          <div className="link-popover-row">
            <input
              id={`link-${ariaLabel.replace(/\s/g, '-')}`}
              autoFocus
              value={linkValue}
              onChange={(event) => { setLinkValue(event.target.value); setLinkError(''); }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  applyLink();
                }
              }}
              placeholder="https://example.com"
              inputMode="url"
            />
            <button type="button" onClick={applyLink}>Apply</button>
          </div>
          {linkError && <span className="link-error">{linkError}</span>}
        </div>
      )}

      {emojiOpen && (
        <div className="rich-emoji-picker">
          <Suspense fallback={<div className="emoji-picker-loading">Loading emojis…</div>}>
            <EmojiPicker
              theme={'auto' as Theme}
              emojiStyle={'native' as EmojiStyle}
              width="100%"
              height={340}
              autoFocusSearch
              lazyLoadEmojis
              previewConfig={{ showPreview: false }}
              onEmojiClick={({ emoji }) => {
                editor.chain().focus().insertContent(emoji).run();
                setEmojiOpen(false);
              }}
            />
          </Suspense>
        </div>
      )}

      {footer && <div className="rich-editor-footer">{footer}</div>}
    </div>
  );
}
