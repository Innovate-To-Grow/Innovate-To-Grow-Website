/**
 * Block-level schedule override for `/schedule` embed widgets.
 *
 * `EmbedWidgetBlock` puts the block's pinned `CurrentProjectSchedule` id on the
 * iframe URL (`/_embed/<slug>?schedule_id=…`) and `EmbedBlockPage` reads it
 * back; both sides accept only a well-formed UUID so nothing else from the
 * query string reaches the schedule API.
 */
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function normalizeScheduleId(value: string | null | undefined): string | null {
  const trimmed = String(value ?? '').trim().toLowerCase();
  return UUID_RE.test(trimmed) ? trimmed : null;
}
