import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ChatProvider } from './contexts/ChatContext'
import { ToastProvider } from './contexts/ToastContext'
import { ChatLayoutProvider } from './contexts/ChatLayoutContext'
import { GlobalChatProvider } from './contexts/GlobalChatContext'
import Layout from './components/layout/Layout'
import FilesPage from './pages/FilesPage'
import NetworkAnalysisPage from './pages/NetworkAnalysisPage'
import ReportsPage from './pages/ReportsPage'

function App() {
  return (
    <Router>
      <ChatProvider>
        <ToastProvider>
          <ChatLayoutProvider>
            <GlobalChatProvider>
              <Layout>
                <Routes>
                  <Route path="/" element={<NetworkAnalysisPage />} />
                  <Route path="/files" element={<FilesPage />} />
                  <Route path="/network-analysis" element={<NetworkAnalysisPage />} />
                  <Route path="/reports" element={<ReportsPage />} />
                </Routes>
              </Layout>
            </GlobalChatProvider>
          </ChatLayoutProvider>
        </ToastProvider>
      </ChatProvider>
    </Router>
  )
}

export default App


