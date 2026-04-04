import axios from 'axios';
import {useEffect, useState} from 'react';

import {fetchCurrentSchedule, type EventSchedulePayload} from './api';

interface UseCurrentEventScheduleResult {
  data: EventSchedulePayload | null;
  loading: boolean;
  error: string | null;
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string' && detail) {
      return detail;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : 'Failed to load event schedule';
}

export function useCurrentEventSchedule(): UseCurrentEventScheduleResult {
  const [data, setData] = useState<EventSchedulePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchCurrentSchedule()
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(getErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return {data, loading, error};
}
