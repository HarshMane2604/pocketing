import type { JSONContent } from '@tiptap/core';
import CharacterCount from '@tiptap/extension-character-count';
import Placeholder from '@tiptap/extension-placeholder';
import TaskItem from '@tiptap/extension-task-item';
import TaskList from '@tiptap/extension-task-list';
import TextAlign from '@tiptap/extension-text-align';
import StarterKit from '@tiptap/starter-kit';

export const richTextBaseExtensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    link: {
      openOnClick: false,
      autolink: true,
      linkOnPaste: true,
      defaultProtocol: 'https',
      HTMLAttributes: {
        rel: 'noopener noreferrer nofollow',
        target: '_blank',
      },
    },
  }),
  TextAlign.configure({
    types: ['heading', 'paragraph'],
    alignments: ['left', 'center', 'right'],
  }),
  TaskList,
  TaskItem.configure({ nested: true }),
];

export function richTextEditorExtensions(placeholder: string, maxLength: number) {
  return [
    ...richTextBaseExtensions,
    Placeholder.configure({ placeholder }),
    CharacterCount.configure({ limit: maxLength, mode: 'textSize' }),
  ];
}

export function plainTextToDocument(value: string): JSONContent {
  const lines = value.replace(/\r\n/g, '\n').split('\n');
  return {
    type: 'doc',
    content: (lines.length ? lines : ['']).map((line) => ({
      type: 'paragraph',
      content: line ? [{ type: 'text', text: line }] : undefined,
    })),
  };
}

export function isRichTextDocument(value: unknown): value is JSONContent {
  return Boolean(value && typeof value === 'object' && (value as JSONContent).type === 'doc');
}

export function normalizeRichTextDocument(document: JSONContent): JSONContent {
  const visit = (node: JSONContent): JSONContent => {
    const hasInlineCode = node.type === 'text'
      && node.marks?.some((mark) => mark.type === 'code');
    const text = hasInlineCode && node.text && node.text.length >= 2
      && node.text.startsWith('`') && node.text.endsWith('`')
      ? node.text.slice(1, -1)
      : node.text;
    return {
      ...node,
      ...(text !== undefined ? { text } : {}),
      ...(node.content ? { content: node.content.map(visit) } : {}),
    };
  };
  return visit(document);
}

function inlineText(node: JSONContent): string {
  if (node.type === 'text') return node.text ?? '';
  if (node.type === 'hardBreak') return '\n';
  return (node.content ?? []).map(inlineText).join('');
}

function renderList(node: JSONContent, depth: number): string {
  const start = Number(node.attrs?.start ?? 1);
  return (node.content ?? []).map((item, index) => {
    const marker = node.type === 'orderedList'
      ? `${start + index}. `
      : node.type === 'taskList'
        ? (item.attrs?.checked ? '☑ ' : '☐ ')
        : '• ';
    const blocks: string[] = [];
    const nested: string[] = [];
    for (const child of item.content ?? []) {
      if (['bulletList', 'orderedList', 'taskList'].includes(child.type ?? '')) {
        const value = renderList(child, depth + 1);
        if (value) nested.push(value);
      } else {
        const value = renderBlock(child, depth);
        if (value) blocks.push(value);
      }
    }
    const lines = blocks.join('\n').split('\n');
    const indent = '  '.repeat(depth);
    const continuation = indent + ' '.repeat(marker.length);
    const rendered = [indent + marker + (lines[0] ?? '')];
    rendered.push(...lines.slice(1).map((line) => continuation + line), ...nested);
    return rendered.join('\n');
  }).join('\n');
}

function renderBlock(node: JSONContent, depth = 0): string {
  if (['paragraph', 'heading', 'codeBlock'].includes(node.type ?? '')) return inlineText(node);
  if (['bulletList', 'orderedList', 'taskList'].includes(node.type ?? '')) return renderList(node, depth);
  if (node.type === 'blockquote') {
    return (node.content ?? []).map((child) => renderBlock(child, depth)).join('\n')
      .split('\n').map((line) => `> ${line}`).join('\n');
  }
  if (node.type === 'horizontalRule') return '────────';
  if (node.type === 'hardBreak') return '\n';
  return inlineText(node);
}

export function richTextToPlainText(document: JSONContent): string {
  return (document.content ?? []).map((node) => renderBlock(node)).join('\n').trim();
}

export function documentIsEmpty(document: JSONContent): boolean {
  const visit = (node: JSONContent): boolean => {
    if (node.type === 'text' && node.text) return false;
    if (node.type === 'horizontalRule') return false;
    if (node.type === 'image') return false;
    return !(node.content ?? []).some((child) => !visit(child));
  };
  return visit(document);
}
