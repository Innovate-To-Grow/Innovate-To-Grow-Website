import {api} from '@/lib/api';
import {
    authApi,
    getAccessToken,
    isDefinitiveAuthFailure,
} from '@/features/auth';
import {pathSegment} from './catalog';
import type {ProjectGridRow, PastProjectShare, PastProjectShareSummary} from './types';

export const createPastProjectShare = async (
    rows: ProjectGridRow[],
    name: string,
    note: string,
): Promise<PastProjectShare> => {
    // The client no longer sends a combined details_text field; the shared snapshot is the rows.
    const response = await authApi.post<PastProjectShare>('/projects/past-shares/', {
        rows,
        name,
        note,
    });
    return response.data;
};

export const fetchPastProjectShare = async (id: string): Promise<PastProjectShare> => {
    if (getAccessToken()) {
        try {
            const response = await authApi.get<PastProjectShare>(`/projects/past-shares/${pathSegment(id)}/`, {
                requireFreshIdentity: true,
            });
            return response.data;
        } catch (err) {
            const status = (err as { response?: { status?: number } }).response?.status;
            if (status !== 401 || !isDefinitiveAuthFailure(err)) {
                throw err;
            }
        }
    }

    const response = await api.get<PastProjectShare>(`/projects/past-shares/${pathSegment(id)}/`);
    return response.data;
};

export const updatePastProjectShare = async (
    id: string,
    payload: Partial<Pick<PastProjectShare, 'name' | 'rows' | 'note'>> &
        Pick<PastProjectShare, 'version'>,
): Promise<PastProjectShare> => {
    const response = await authApi.patch<PastProjectShare>(`/projects/past-shares/${pathSegment(id)}/`, payload);
    return response.data;
};

export const listMyShares = async (): Promise<PastProjectShareSummary[]> => {
    const response = await authApi.get<PastProjectShareSummary[]>('/projects/past-shares/mine/');
    return response.data;
};

export const deleteShare = async (id: string): Promise<void> => {
    await authApi.delete(`/projects/past-shares/${pathSegment(id)}/`);
};
