import { createContext, useContext } from 'react';

export interface HealthCheckContextType {
  isHealthy: boolean;
  isLoading: boolean;
  checkNow: () => Promise<void>;
}

export const HealthCheckContext = createContext<HealthCheckContextType>({
  isHealthy: true,
  isLoading: true,
  checkNow: async () => {},
});

export const useHealthCheck = () => useContext(HealthCheckContext);


