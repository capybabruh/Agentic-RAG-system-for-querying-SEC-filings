import { Navigate, Outlet, useLocation } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"

export function ProtectedRoute() {
  const { loading, session } = useAuth()
  const location = useLocation()

  if (loading) {
    return <main className="grid min-h-screen place-items-center">Loading...</main>
  }

  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
