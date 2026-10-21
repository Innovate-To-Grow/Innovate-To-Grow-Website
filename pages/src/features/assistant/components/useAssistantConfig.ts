import {useEffect, useRef, useState} from 'react';

import {DEFAULT_ASSISTANT_CONFIG, fetchAssistantConfig, type AssistantConfig} from '@/features/assistant/api';
import {isIsolatedRoute} from '@/lib/isolatedRoute';

/**
 * The assistant's public config, fetched once the visitor first interacts (or the browser is idle);
 * the hardcoded defaults stand until then, and if the request fails.
 */
export function useAssistantConfig(): AssistantConfig {
  const [config, setConfig] = useState<AssistantConfig>(DEFAULT_ASSISTANT_CONFIG);
  const configStartedRef = useRef(false);

  useEffect(() => {
    if (isIsolatedRoute()) return;
    let cancelled = false;
    function cleanupInteractionListeners() {
      window.removeEventListener('pointerdown', start);
      window.removeEventListener('keydown', start);
      window.removeEventListener('i2g-assistant-interaction', start);
    }
    function start() {
      if (configStartedRef.current || cancelled || isIsolatedRoute()) return;
      configStartedRef.current = true;
      cleanupInteractionListeners();
      void fetchAssistantConfig()
        .then((cfg) => {
          if (!cancelled) setConfig(cfg);
        })
        .catch(() => {
          /* keep DEFAULT_ASSISTANT_CONFIG */
        });
    }
    window.addEventListener('pointerdown', start, {once: true, passive: true});
    window.addEventListener('keydown', start, {once: true});
    window.addEventListener('i2g-assistant-interaction', start, {once: true});
    const idleId = 'requestIdleCallback' in window
      ? window.requestIdleCallback(start, {timeout: 3000})
      : undefined;
    const timerId = idleId === undefined ? window.setTimeout(start, 2000) : undefined;
    return () => {
      cancelled = true;
      cleanupInteractionListeners();
      if (idleId !== undefined) window.cancelIdleCallback(idleId);
      if (timerId !== undefined) window.clearTimeout(timerId);
    };
  }, []);

  return config;
}
