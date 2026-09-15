import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AuthProvider } from "@/auth/AuthProvider"
import { ProtectedRoute } from "@/auth/ProtectedRoute"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AuthPage } from "@/pages/AuthPage"
import { ChatPage } from "@/pages/ChatPage"

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <TooltipProvider>
          <Routes>
            <Route path="/login" element={<AuthPage mode="login" />} />
            <Route path="/signup" element={<AuthPage mode="signup" />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/app" element={<ChatPage />} />
              <Route path="/app/thread/:threadId" element={<ChatPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Routes>
        </TooltipProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
