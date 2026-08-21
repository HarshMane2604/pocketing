import { useMemo } from 'react';
import type { JSONContent } from '@tiptap/core';
import { renderToHTMLString } from '@tiptap/static-renderer/pm/html-string';

import { normalizeRichTextDocument, richTextBaseExtensions } from '@/components/richTextExtensions';
import { sanitizeRichTextHtml } from '@/components/richTextSanitize';

interface RichTextDisplayProps {
  content: JSONContent;
  className?: string;
}

export function RichTextDisplay({ content, className = '' }: RichTextDisplayProps) {
  const sanitizedHtml = useMemo(() => {
    try {
      const html = renderToHTMLString({
        content: normalizeRichTextDocument(content),
        extensions: richTextBaseExtensions,
      });
      const sanitized = sanitizeRichTextHtml(html);
      const parsed = new DOMParser().parseFromString(sanitized, 'text/html');
      parsed.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]').forEach((input) => {
        input.disabled = true;
      });
      return parsed.body.innerHTML;
    } catch {
      return '';
    }
  }, [content]);

  return (
    <div
      className={`rich-text-display custom-prose ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
    />
  );
}
