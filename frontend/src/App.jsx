import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ChatProvider } from './contexts/ChatContext'
import Layout from './components/layout/Layout'
import ChatPage from './pages/ChatPage'
import FilesPage from './pages/FilesPage'
import NetworkAnalysisPage from './pages/NetworkAnalysisPage'

function App() {
  return (
    <Router>
      <ChatProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/files" element={<FilesPage />} />
            <Route path="/network-analysis" element={<NetworkAnalysisPage />} />
          </Routes>
        </Layout>
      </ChatProvider>
    </Router>
  )
}

export default App

