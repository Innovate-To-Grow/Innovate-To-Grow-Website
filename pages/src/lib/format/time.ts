/**
 * Time helpers shared between the schedule page and the schedule grid.
 *
 * `addMinutes` takes an `H:MM` string and returns the time N minutes later,
 * wrapping past 12 (the event schedule is rendered in 12-hour local time).
 */
export const addMinutes = (time: string, minutes: number): string => {
  const [hoursRaw, minsRaw] = time.split(':').map(Number);
  let hours = hoursRaw;
  let mins = minsRaw + minutes;

  while (mins >= 60) {
    hours += 1;
    mins -= 60;
  }
  if (hours > 12) {
    hours -= 12;
  }
  const pad = mins < 10 ? `0${mins}` : `${mins}`;
  return `${hours}:${pad}`;
};
