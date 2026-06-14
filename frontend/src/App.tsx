import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import PatientsPage from "./pages/PatientsPage";
import TrialMatchPage from "./pages/TrialMatchPage";

function NavBar() {
  return (
    <header className="bg-blue-800 text-white px-6 py-3 flex items-center justify-between shadow">
      <div className="flex items-center gap-3">
        <span className="text-lg font-semibold tracking-tight">
          🧬 Clinical Trial Matcher
        </span>
      </div>
      <span className="text-sm text-blue-200">Demo — Dr. Sarah Chen</span>
    </header>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <NavBar />
        <main className="flex-1 p-6 max-w-5xl mx-auto w-full">
          <Routes>
            <Route path="/" element={<Navigate to="/patients" replace />} />
            <Route path="/patients" element={<PatientsPage />} />
            <Route path="/patients/:patientId/match" element={<TrialMatchPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
