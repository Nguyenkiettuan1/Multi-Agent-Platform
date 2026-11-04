import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminLayout } from '../components/layout/AdminLayout'
import { UserLayout } from '../components/layout/UserLayout'
import { DashboardPage } from '../pages/admin/DashboardPage'
import { KnowledgePage } from '../pages/admin/KnowledgePage'
import { KnowledgeDocumentPage } from '../pages/admin/KnowledgeDocumentPage'
import { FeedbackPage } from '../pages/admin/FeedbackPage'
import { AuditPage } from '../pages/admin/AuditPage'
import { ModelsPage } from '../pages/admin/ModelsPage'
import { LogsPage } from '../pages/admin/LogsPage'
import { SupportPage } from '../pages/admin/SupportPage'
import { ChatPage } from '../pages/chat/ChatPage'
import { SettingsPage } from '../pages/settings/SettingsPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/chat" replace />} />

      <Route element={<UserLayout />}>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:sessionId" element={<ChatPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="knowledge/:docId" element={<KnowledgeDocumentPage />} />
        <Route path="feedback" element={<FeedbackPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="support" element={<SupportPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
