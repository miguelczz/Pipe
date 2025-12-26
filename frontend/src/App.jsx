import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { ChatProvider } from './contexts/ChatContext'
import Layout from './components/layout/Layout'
import ToolsPage from './pages/ToolsPage'
import DashboardPage from './pages/DashboardPage'
import GeoTracePage from './pages/GeoTracePage'
import ChatPage from './pages/ChatPage'
import FilesPage from './pages/FilesPage'

function App() {
  return (
    <Router>
      <ChatProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/geotrace" element={<GeoTracePage />} />
            <Route path="/files" element={<FilesPage />} />
            <Route path="/tools" element={<ToolsPage />} />
          </Routes>
        </Layout>
      </ChatProvider>
    </Router>
  )
}

export default App

