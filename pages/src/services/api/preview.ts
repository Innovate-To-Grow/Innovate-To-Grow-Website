import api from './client';

// ======================== Preview ========================

export interface PreviewTokenValidationResponse {
  valid: boolean;
  detail?: string;
}

export const validatePreviewToken = async (token: string, objectId?: string): Promise<boolean> => {
  try {
    const response = await api.post<PreviewTokenValidationResponse>('/pages/preview/validate-token/', { token, objectId });
    return response.data.valid;
  } catch {
    return false;
  }
};

export interface PreviewDataResponse {
  html: string;
  css: string;
  timestamp: number;
}

export const fetchPreviewData = async (sessionId: string): Promise<PreviewDataResponse | null> => {
  try {
    const response = await api.get<PreviewDataResponse>('/pages/preview/data/', { params: { sessionId } });
    return response.data;
  } catch {
    return null;
  }
};

// ======================== Token-Based Preview ========================

export interface TokenPreviewResponse {
  id: string;
  title?: string;
  name?: string;
  slug?: string;
  html: string;
  css: string;
  dynamic_config?: Record<string, unknown>;
  status: string;
  is_preview: boolean;
}

export const fetchPreviewByToken = async (token: string): Promise<TokenPreviewResponse | null> => {
  try {
    const response = await api.get<TokenPreviewResponse>(`/pages/preview/${token}/`);
    return response.data;
  } catch {
    return null;
  }
};
