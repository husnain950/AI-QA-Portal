import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 30_000,
            gcTime: 5 * 60_000,
            // ONE retry layer, not two. `api.get` already retries once via
            // `onceOrRetry`, and `documentStore` goes through both -- so an
            // unreachable API took 6 requests x a 15s timeout plus backoffs, about
            // 90 seconds, before the review page's spinner could resolve to
            // anything. The client-level retry is the one that stays, because it is
            // the one that knows which statuses are transient.
            retry: false,
            refetchOnWindowFocus: false,
        },
        mutations: { retry: false },
    },
});
