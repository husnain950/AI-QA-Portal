import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 30_000,
            gcTime: 5 * 60_000,
            retry: (count, error) => count < 2 && error?.retryable,
            refetchOnWindowFocus: false,
        },
        mutations: { retry: false },
    },
});
