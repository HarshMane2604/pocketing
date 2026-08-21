import DOMPurify from 'dompurify';

const SAFE_STYLE_PROPERTIES = new Set([
  'font-style',
  'font-weight',
  'text-align',
  'text-decoration',
  'text-decoration-line',
  'white-space',
]);

const SAFE_STYLE_VALUES: Record<string, RegExp> = {
  'font-style': /^(?:normal|italic|oblique)$/i,
  'font-weight': /^(?:normal|bold|[1-9]00)$/i,
  'text-align': /^(?:left|center|right)$/i,
  'text-decoration': /^(?:(?:none|underline|line-through)(?:\s+|$))+$/i,
  'text-decoration-line': /^(?:(?:none|underline|line-through)(?:\s+|$))+$/i,
  'white-space': /^(?:normal|pre|pre-wrap)$/i,
};

/** Sanitize HTML first, then retain only formatting CSS the editor understands. */
export function sanitizeRichTextHtml(html: string): string {
  const sanitized = DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'svg', 'math'],
    FORBID_ATTR: ['onerror', 'onload', 'srcdoc'],
  });
  const parsed = new DOMParser().parseFromString(sanitized, 'text/html');

  parsed.body.querySelectorAll<HTMLElement>('[style]').forEach((element) => {
    const safeDeclarations: string[] = [];
    for (const property of SAFE_STYLE_PROPERTIES) {
      const value = element.style.getPropertyValue(property).trim();
      if (value && SAFE_STYLE_VALUES[property].test(value)) {
        safeDeclarations.push(`${property}: ${value}`);
      }
    }
    if (safeDeclarations.length) element.setAttribute('style', safeDeclarations.join('; '));
    else element.removeAttribute('style');
  });

  return parsed.body.innerHTML;
}
