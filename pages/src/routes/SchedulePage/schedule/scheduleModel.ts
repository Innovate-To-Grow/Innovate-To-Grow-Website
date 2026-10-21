import type {ScheduleSection, ScheduleTrack} from '@/features/events/api';
import {addMinutes} from '@/lib/format';

const SECTION_ORDER = ['CAP', 'CEE', 'ENGSL', 'CSE'] as const;
const GRAND_AWARD_LABELS: Record<string, string> = {
  CAP: 'F3 Innovate Engineering Award',
  CSE: 'F3 Innovate Software Award',
  CEE: 'F3 Innovate Civil & Environmental Award',
  ENGSL: 'F3 Innovate Engineering Award',
};

export const grandAwardLabel = (sectionCode: string) => GRAND_AWARD_LABELS[sectionCode] ?? 'F3 Innovate Award';

/** Known classes in their fixed order, then any others by their display order. */
export function orderSections(sections: ScheduleSection[]): ScheduleSection[] {
  const orderMap = new Map<string, number>(SECTION_ORDER.map((code, index) => [code, index]));
  return [...sections].sort((left, right) => {
    const leftRank = orderMap.get(left.code) ?? left.display_order + 100;
    const rightRank = orderMap.get(right.code) ?? right.display_order + 100;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return left.display_order - right.display_order;
  });
}

function buildTimeSlots(startTime: string, slotMinutes: number, maxOrder: number): string[] {
  const slots: string[] = [];
  let currentTime = startTime;
  for (let order = 1; order <= maxOrder; order += 1) {
    slots.push(currentTime);
    currentTime = addMinutes(currentTime, slotMinutes);
  }
  return slots;
}

function isFullyEmptyOrder(tracks: Array<{slots: Array<{order: number}>}>, order: number): boolean {
  return tracks.length > 0 && tracks.every((track) => !track.slots.some((slot) => slot.order === order));
}

export interface PresentationGrid {
  tracks: ScheduleTrack[];
  /** Start time of each slot; slot `order` N is `times[N - 1]`. */
  times: string[];
  /** Orders where no track presents: shown as a Break across the whole row. */
  fullyEmptyOrders: Set<number>;
  showTopicRow: boolean;
}

/** One class's presentation grid: its tracks in display order and its time slots. */
export function presentationGrid(section: ScheduleSection): PresentationGrid {
  const tracks = [...section.tracks].sort(
    (left, right) => left.display_order - right.display_order || left.track_number - right.track_number,
  );
  const times = buildTimeSlots(section.start_time, section.slot_minutes, section.max_order);
  const fullyEmptyOrders = new Set(
    times.map((_, index) => index + 1).filter((order) => isFullyEmptyOrder(tracks, order)),
  );
  return {tracks, times, fullyEmptyOrders, showTopicRow: tracks.some((track) => track.topic)};
}
