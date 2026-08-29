import React, { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import DialogHost from './components/ui/Dialog';
import ToastHost from './components/ui/ToastHost';
import { setUnauthorizedHandler } from './utils/api';
import { authApi } from './utils/auth';
import { queryClient } from './queryClient';
import { useUiStore } from './stores/uiStore';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const UploadPage = lazy(() => import('./pages/UploadPage'));
const ReviewPage = lazy(() => import('./pages/ReviewPage'));
const TriagePage = lazy(() => import('./pages/TriagePage'));
const TimelinePage = lazy(() => import('./pages/TimelinePage'));

const PageLoader = () => (
  <div className="route-loader" role="status" aria-live="polite">
    Loading workspace…
  </div>
);

function App() {
  // undefined = still asking the server, null = signed out, object = signed in.
  const [user, setUser] = useState(undefined);
  const setReviewerName = useUiStore((state) => state.setReviewerName);

  const signedOut = useCallback(() => {
    setUser(null);
    setReviewerName('');
    // Cached pages belong to the previous session; the next one must refetch.
    queryClient.clear();
  }, [setReviewerName]);

  useEffect(() => {
    setUnauthorizedHandler(signedOut);
    return () => setUnauthorizedHandler(null);
  }, [signedOut]);

  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((principal) => {
        if (cancelled) return;
        setUser(principal);
        setReviewerName(principal ? principal.display_name || principal.email : '');
      })
      .catch(() => !cancelled && setUser(null));
    return () => {
      cancelled = true;
    };
  }, [setReviewerName]);

  const signedIn = useCallback(
    (principal) => {
      setUser(principal);
      setReviewerName(principal.display_name || principal.email);
    },
    [setReviewerName],
  );

  if (user === undefined) return <PageLoader />;
  if (user === null) {
    return (
      <>
        <ToastHost />
        <LoginPage onSignedIn={signedIn} />
      </>
    );
  }

  return (
    <BrowserRouter>
      <DialogHost />
      <ToastHost />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<TriagePage />} />
          <Route path="/library" element={<DashboardPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/review/:documentId/:sectionId?" element={<ReviewPage />} />
          <Route path="/timeline" element={<TimelinePage />} />
          <Route path="/timeline/:family/:sectionCode" element={<TimelinePage />} />
          <Route path="/timeline/*" element={<TimelinePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
