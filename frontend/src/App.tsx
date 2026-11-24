import React, { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { DemoAuthGate } from './contexts/DemoAuthGate';
import { AuthScreen } from './components/AuthScreen';
import { DemoDashboard } from './components/DemoDashboard';
import { Navbar } from './components/Navbar';
import { TopicsAssessmentsView } from './components/teacher/TopicsAssessmentsView';
import { SubmissionsOCRView } from './components/teacher/SubmissionsOCRView';
import { AnswerMatchingView } from './components/teacher/AnswerMatchingView';
import { EvaluationsView } from './components/teacher/EvaluationsView';
import { RemediationsView } from './components/teacher/RemediationsView';
import { InterventionOutcomesView } from './components/teacher/InterventionOutcomesView';
import { StudentPracticeView } from './components/student/StudentPracticeView';
import { AdminOverviewView } from './components/admin/AdminOverviewView';
import { ReviewQueue } from './components/teacher/ReviewQueue';
import { MisconceptionClusters } from './components/teacher/MisconceptionClusters';

export interface MainAppProps {
  initialPath?: string;
}

export const MainApp: React.FC<MainAppProps> = ({ initialPath }) => {
  const { user, isLoading } = useAuth();
  const [currentPath, setCurrentPath] = useState<string>(() => {
    if (initialPath) return initialPath;
    if (typeof window !== 'undefined' && window.location) {
      return window.location.pathname || '/';
    }
    return '/';
  });
  const [activeTab, setActiveTab] = useState<string>('dashboard');

  const navigate = (path: string) => {
    if (typeof window !== 'undefined' && window.location && window.history) {
      if (window.location.pathname !== path) {
        window.history.pushState({}, '', path);
      }
    }
    setCurrentPath(path);
  };

  useEffect(() => {
    const handlePopState = () => {
      if (typeof window !== 'undefined' && window.location) {
        setCurrentPath(window.location.pathname || '/');
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true';
  const isAuthenticated = Boolean(user);

  // Synchronize route transitions
  useEffect(() => {
    if (isLoading) return;

    if (currentPath === '/' || currentPath === '') {
      if (isDemoMode && isAuthenticated) {
        navigate('/dashboard');
      } else if (!isDemoMode && isAuthenticated) {
        navigate('/dashboard');
      } else {
        navigate('/login');
      }
    } else if (currentPath === '/login') {
      if (isDemoMode && isAuthenticated) {
        navigate('/dashboard');
      }
    } else {
      // Any other protected route (e.g. /dashboard)
      if (!isAuthenticated) {
        navigate('/login');
      }
    }
  }, [currentPath, isDemoMode, isAuthenticated, isLoading]);

  if (isLoading) {
    return (
      <div className="loading-container" style={{ minHeight: '100vh' }}>
        <span className="spinner" style={{ width: '32px', height: '32px' }} />
      </div>
    );
  }

  // Render Login Route
  if (currentPath === '/login' && (!isDemoMode || !isAuthenticated)) {
    return (
      <AuthScreen
        onLoginSuccess={() => {
          navigate('/dashboard');
        }}
      />
    );
  }

  // Render Protected Dashboard & Views
  return (
    <div className="app-container" data-testid="dashboard-view">
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />
      <main className="main-content">
        {activeTab === 'dashboard' && <DemoDashboard />}
        {activeTab === 'assessments' && <TopicsAssessmentsView />}
        {activeTab === 'submissions' && <SubmissionsOCRView />}
        {activeTab === 'matching' && <AnswerMatchingView />}
        {activeTab === 'review-queue' && <ReviewQueue />}
        {activeTab === 'evaluations' && <EvaluationsView />}
        {activeTab === 'clusters' && <MisconceptionClusters />}
        {activeTab === 'remediations' && <RemediationsView />}
        {activeTab === 'outcomes' && <InterventionOutcomesView />}
        {activeTab === 'practice' && <StudentPracticeView />}
        {activeTab === 'admin' && <AdminOverviewView />}
      </main>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <DemoAuthGate>
        <MainApp />
      </DemoAuthGate>
    </AuthProvider>
  );
};

export default App;
