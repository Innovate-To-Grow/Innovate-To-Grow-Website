import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { HealthCheckProvider } from './components/HealthCheck/HealthCheckProvider';
import './App.css';

export const App = () => {
  return (
    <HealthCheckProvider pollingInterval={10000}>
      <RouterProvider router={router} />
    </HealthCheckProvider>
  );
};
