import React, { useState } from 'react';
import UploadGazette from './pages/UploadGazette';
import SearchResults from './pages/SearchResults';

const NAV_ITEMS = [
  { id: 'upload', label: 'Upload & Map PDF' },
  { id: 'search', label: 'Search Records' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('search');

  return (
    <div className="min-h-screen bg-bg text-ink">
      <header className="sticky top-0 z-20 border-b border-border bg-bg">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:h-16 sm:flex-nowrap sm:py-0 sm:px-6 lg:px-8">
          <div className="flex shrink-0 items-center gap-2.5 whitespace-nowrap">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center border border-border-strong text-[10px] font-semibold">
              BG
            </span>
            <p className="text-sm font-semibold tracking-tight text-ink">
              BISE Gazette Admin
            </p>
          </div>

          <nav className="flex items-stretch gap-1" aria-label="Primary">
            {NAV_ITEMS.map((item) => {
              const active = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveTab(item.id)}
                  aria-current={active ? 'page' : undefined}
                  className={`whitespace-nowrap border px-3 py-1.5 text-xs font-medium transition-colors sm:text-sm ${
                    active
                      ? 'border-border-strong bg-ink text-bg'
                      : 'border-transparent text-ink-muted hover:border-border hover:text-ink'
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      <main className="py-8 sm:py-10">
        {activeTab === 'upload' ? <UploadGazette /> : <SearchResults />}
      </main>
    </div>
  );
}
