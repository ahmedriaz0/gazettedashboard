import React, { useState } from 'react';
import UploadGazette from './pages/UploadGazette';
import SearchResults from './pages/SearchResults';

export default function App() {
  const [activeTab, setActiveTab] = useState('search');

  return (
    <div className="min-h-screen bg-slate-50 font-sans">
      {/* Top Navigation Bar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 bg-blue-600 rounded-full inline-block"></span>
            <h3 className="text-lg font-extrabold text-slate-900 tracking-tight">
              BISE Gazette Admin
            </h3>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex gap-2">
            <button
              onClick={() => setActiveTab('upload')}
              className={`px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg transition ${
                activeTab === 'upload'
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              Page 1: Upload & Map PDF
            </button>
            <button
              onClick={() => setActiveTab('search')}
              className={`px-4 py-2 text-xs sm:text-sm font-semibold rounded-lg transition ${
                activeTab === 'search'
                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              Page 2: Search Results
            </button>
          </nav>
        </div>
      </header>

      {/* Main View Area */}
      <main className="py-8">
        {activeTab === 'upload' ? <UploadGazette /> : <SearchResults />}
      </main>
    </div>
  );
}