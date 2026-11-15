const URL_SCHEME_RE = /^[A-Za-z][A-Za-z0-9+.-]*:/;

function hasControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => {
    const code = character.charCodeAt(0);
    return code <= 0x1f || code === 0x7f;
  });
}

export function normalizeCMSRoute(route: string): string {
  const trimmed = route.trim();
  if (!trimmed || trimmed === '/') {
    return '/';
  }

  if (
    URL_SCHEME_RE.test(trimmed)
    || trimmed.startsWith('//')
    || trimmed.includes('\\')
    || trimmed.includes('?')
    || trimmed.includes('#')
    || hasControlCharacter(trimmed)
  ) {
    throw new Error('CMS route must be a safe site-relative pathname.');
  }

  const segments = trimmed.split('/').filter(Boolean).map((segment) => {
    let decoded: string;
    try {
      decoded = decodeURIComponent(segment);
    } catch {
      throw new Error('CMS route contains invalid percent encoding.');
    }

    if (
      decoded === '.'
      || decoded === '..'
      || decoded.includes('/')
      || decoded.includes('\\')
      || hasControlCharacter(decoded)
    ) {
      throw new Error('CMS route contains an unsafe path segment.');
    }
    return decoded;
  });

  return segments.length > 0 ? `/${segments.join('/')}` : '/';
}
