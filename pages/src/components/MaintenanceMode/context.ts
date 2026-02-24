import { createContext, useContext } from 'react';

export interface HealthCheckContextType {
  isHealthy: boolean;
  isLoading: boolean;
  maintenance: boolean;
  maintenanceMessage: string;
  checkNow: () => Promise<void>;
}

export const HealthCheckContext = createContext<HealthCheckContextType>({
  isHealthy: true,
  isLoading: true,
  maintenance: false,
  maintenanceMessage: '',
  checkNow: async () => {},
});

export const useHealthCheck = () => useContext(HealthCheckContext);
