import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ChatProvider } from './contexts/ChatContext'
import { ToastProvider } from './contexts/ToastContext'
import Layout from './components/layout/Layout'
import ChatPage from './pages/ChatPage'
import FilesPage from './pages/FilesPage'
import NetworkAnalysisPage from './pages/NetworkAnalysisPage'
import ReportsPage from './pages/ReportsPage'
import ToolsPage from './pages/ToolsPage'

function App() {
  return (
    <Router>
      <ChatProvider>
        <ToastProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/files" element={<FilesPage />} />
            <Route path="/network-analysis" element={<NetworkAnalysisPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/tools" element={<ToolsPage />} />
          </Routes>
        </Layout>
        </ToastProvider>
      </ChatProvider>
    </Router>
  )
}

export default App

