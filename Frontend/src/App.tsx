import { BrowserRouter as Router, Routes, Route, Outlet } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import Home from './pages/Home';
import Upload from './pages/Upload';
import Processing from './pages/Processing';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import Player from './pages/Player';
import Layout from './components/Layout';
import { ProjectProvider } from './context/ProjectContext';
import { AuthProvider } from './context/AuthContext';

const PlatformLayout = () => (
  <ProjectProvider>
    <Layout>
      <AnimatePresence mode="wait">
        <Outlet />
      </AnimatePresence>
    </Layout>
  </ProjectProvider>
);

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="app-noise" />
        <Routes>
          {/* Public */}
          <Route path="/" element={<Home />} />

          {/* Platform Routes (with Sidebar) */}
          <Route element={<PlatformLayout />}>
            <Route path="/dashboard"  element={<Dashboard />} />
            <Route path="/upload"     element={<Upload />} />
            <Route path="/processing" element={<Processing />} />
            <Route path="/history"    element={<History />} />
            <Route path="/player/:id" element={<Player />} />
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
