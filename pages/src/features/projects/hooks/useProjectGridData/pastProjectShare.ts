import {useCallback, useEffect, useMemo, useState} from 'react';
import {fetchPastProjectShare, type PastProjectShare} from '@/features/projects/api';

interface PastProjectShareResult {
    share: PastProjectShare | null;
    loading: boolean;
    error: string | null;
    /** The share does not exist (deleted, or a wrong or incomplete link), as opposed to a failed request. */
    notFound: boolean;
    /** Loads the share again after a failed request. */
    retry: () => void;
}

export const responseStatus = (error: unknown) => (error as {response?: {status?: number}} | null)?.response?.status;

interface PastProjectShareState {
    requestKey: symbol | null;
    share: PastProjectShare | null;
    error: string | null;
    notFound: boolean;
}

/** A share id the API does not know (404), or one it cannot parse (400): the link itself is wrong. */
const isMissingShareError = (error: unknown) => {
    const status = responseStatus(error);
    return status === 404 || status === 400;
};

/**
 * The share state, with `seed` put in it as the answer to `requestKey` when it is the share at `shareId`, once per
 * seed. Set while rendering, so the seed is there on the first render and the load never requests it (see
 * https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes).
 */
function useSeededShareState(shareId: string | undefined, requestKey: symbol | null, seed: PastProjectShare | null) {
    const [state, setState] = useState<PastProjectShareState>({
        requestKey: null,
        share: null,
        error: null,
        notFound: false,
    });
    const [usedSeed, setUsedSeed] = useState<PastProjectShare | null>(null);
    if (requestKey && seed?.id === shareId && seed !== usedSeed) {
        setUsedSeed(seed);
        setState({requestKey, share: seed, error: null, notFound: false});
    }
    return [state, setState] as const;
}

/**
 * The share at `shareId`. A `seed` is a share the caller already holds (the one a save just created): when it is the
 * share at `shareId` it stands in for loading it, so the page shows it without asking the server again. Each seed
 * stands in once; Try Again (`retry`) loads the share from the server.
 */
export function usePastProjectShareData(
    shareId: string | undefined,
    seed: PastProjectShare | null = null,
): PastProjectShareResult {
    const [attempt, setAttempt] = useState(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- attempt forces a new Symbol so retry() loads again
    const requestKey = useMemo(() => (shareId ? Symbol(shareId) : null), [shareId, attempt]);
    const [state, setState] = useSeededShareState(shareId, requestKey, seed);

    const retry = useCallback(() => setAttempt((count) => count + 1), []);
    const hasResolved = requestKey !== null && state.requestKey === requestKey;

    useEffect(() => {
        if (!requestKey || !shareId || hasResolved) {
            return;
        }

        let cancelled = false;

        fetchPastProjectShare(shareId)
            .then((result) => {
                if (cancelled) return;
                setState({
                    requestKey,
                    share: result,
                    error: null,
                    notFound: false,
                });
            })
            .catch((err) => {
                if (cancelled) return;
                setState({
                    requestKey,
                    share: null,
                    error: err instanceof Error ? err.message : 'Failed to load shared past projects',
                    notFound: isMissingShareError(err),
                });
            });

        return () => {
            cancelled = true;
        };
    }, [requestKey, shareId, hasResolved, setState]);

    if (!requestKey) {
        return {share: null, loading: false, error: null, notFound: false, retry};
    }

    return {
        share: hasResolved ? state.share : null,
        loading: !hasResolved,
        error: hasResolved ? state.error : null,
        notFound: hasResolved && state.notFound,
        retry,
    };
}
