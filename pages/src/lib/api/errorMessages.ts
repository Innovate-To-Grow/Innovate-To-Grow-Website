/**
 * Every message in a DRF validation body (`{"field": ["msg", ...], "other": "msg"}`), in field order,
 * keeping those `accept` allows. `skipKeys` names non-message fields such as `code` or `retry_after`.
 * A DRF array body (`["msg"]`, a non-field ValidationError) is read like a field map. A body that is not an
 * object at all (a plain-text or HTML error page) yields nothing: iterating a string would otherwise return
 * it one character per "field".
 */
export function collectFieldMessages(
  data: Record<string, unknown>,
  accept: (message: string) => boolean,
  skipKeys: readonly string[] = [],
): string[] {
  const messages: string[] = [];
  if (typeof data !== 'object' || data === null) return messages;
  for (const [key, value] of Object.entries(data)) {
    if (skipKeys.includes(key)) continue;
    const candidates = Array.isArray(value) ? value : [value];
    for (const item of candidates) {
      if (typeof item === 'string' && accept(item)) messages.push(item);
    }
  }
  return messages;
}
