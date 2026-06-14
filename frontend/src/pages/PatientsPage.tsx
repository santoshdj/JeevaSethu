import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchPatients, type Patient } from "../lib/api";

export default function PatientsPage() {
  const [search, setSearch] = useState("");
  const [submitted, setSubmitted] = useState("");
  const navigate = useNavigate();

  const { data: patients, isLoading, isError, error } = useQuery({
    queryKey: ["patients", submitted],
    queryFn: () => fetchPatients(submitted || undefined),
  });

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(search.trim());
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Cancer Patients</h1>
      <p className="text-gray-500 text-sm mb-5">
        Select a patient to find matching clinical trials via Foundry Agent + Foundry IQ.
      </p>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2 mb-6">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name…"
          className="border border-gray-300 rounded px-3 py-2 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          className="bg-blue-700 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-800"
        >
          Search
        </button>
        {submitted && (
          <button
            type="button"
            onClick={() => { setSearch(""); setSubmitted(""); }}
            className="text-gray-500 text-sm underline px-2"
          >
            Clear
          </button>
        )}
      </form>

      {/* States */}
      {isLoading && (
        <div className="text-center py-16 text-gray-400">Loading patients…</div>
      )}
      {isError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded p-4 text-sm">
          {String(error)}
        </div>
      )}

      {/* Table */}
      {patients && patients.length === 0 && (
        <div className="text-center py-16 text-gray-400">No patients found.</div>
      )}
      {patients && patients.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Age</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Sex</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">DOB</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {patients.map((p: Patient, i: number) => (
                <tr
                  key={p.id}
                  className={`border-b border-gray-100 hover:bg-blue-50 cursor-pointer transition-colors ${
                    i % 2 === 0 ? "bg-white" : "bg-gray-50/50"
                  }`}
                  onClick={() => navigate(`/patients/${p.id}/match`)}
                >
                  <td className="px-4 py-3 font-medium text-blue-800">{p.name}</td>
                  <td className="px-4 py-3 text-gray-700">{p.age} yrs</td>
                  <td className="px-4 py-3 text-gray-700">{p.sex}</td>
                  <td className="px-4 py-3 text-gray-500">{p.dob}</td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-blue-600 text-xs font-medium hover:underline">
                      Find trials →
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
