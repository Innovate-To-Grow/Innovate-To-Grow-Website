import api from './client';

// ======================== Health Check ========================

export interface HealthCheckResponse {
  status: 'ok' | 'error' | 'maintenance';
  database: string;
  maintenance: boolean;
  maintenance_message: string;
}

export interface HealthStatus {
  isHealthy: boolean;
  maintenance: boolean;
  maintenanceMessage: string;
}

export const checkHealth = async (): Promise<HealthStatus> => {
  try {
    const response = await api.get<HealthCheckResponse>('/healthy/', {
      timeout: 5000, // 5 second timeout
    });
    return {
      isHealthy: response.data.status === 'ok',
      maintenance: response.data.maintenance ?? false,
      maintenanceMessage: response.data.maintenance_message ?? '',
    };
  } catch (error) {
    // axios wraps non-2xx responses in an error, but 503 still has data
    if (error && typeof error === 'object' && 'response' in error) {
      const resp = (error as { response?: { data?: HealthCheckResponse } }).response;
      if (resp?.data?.maintenance) {
        return {
          isHealthy: false,
          maintenance: true,
          maintenanceMessage: resp.data.maintenance_message ?? '',
        };
      }
    }
    return { isHealthy: false, maintenance: false, maintenanceMessage: '' };
  }
};
