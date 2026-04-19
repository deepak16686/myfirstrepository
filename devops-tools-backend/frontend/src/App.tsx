/**
 * App is intentionally thin — main.tsx owns the providers, router.tsx owns routing.
 * This file exists so consumers can import <App /> for testing/storybooks.
 */
import { RouterProvider } from 'react-router-dom';
import { router } from './router';

export default function App(): React.ReactElement {
  return <RouterProvider router={router} />;
}
