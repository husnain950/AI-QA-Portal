import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import DialogHost from './components/ui/Dialog';
import ToastHost from './components/ui/ToastHost';

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
          <Route path="/timeline/:family/:sectionCode" element={<TimelinePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
