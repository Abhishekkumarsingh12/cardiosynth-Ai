import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import ECGStudio from "./pages/ECGStudio.jsx";
import Reports from "./pages/Reports.jsx";
import Synthetic from "./pages/Synthetic.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import Monitor from "./pages/Monitor.jsx";
import History from "./pages/History.jsx";

function ProtectedRoute({ children }) {
  const { token, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-clinical-950 text-clinical-muted">
        Loading…
      </div>
    );
  }
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        element={
          <ProtectedRoute>
            <Outlet />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="monitor" element={<Monitor />} />
        <Route path="history" element={<History />} />
        <Route path="studio" element={<ECGStudio />} />
        <Route path="reports" element={<Reports />} />
        <Route path="synthetic" element={<Synthetic />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
