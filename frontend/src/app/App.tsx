/** App shell: header, theme toggle, routing between the bookings list and one booking. Owner: Jian. */
import { useEffect, useState } from 'react'
import './App.css'
import { BookingDetail } from '../features/booking/BookingDetail.tsx'
import { BookingsList } from '../features/booking/BookingsList.tsx'
import type { BookingsApi } from './dataSource.ts'
import { useConversations } from './conversations.ts'
import { createFixtureApi } from './fixtures.ts'
import { createHttpApi } from './httpApi.ts'
import { listHref, parseHash, useHash } from './route.ts'

type Theme = 'light' | 'dark'
const THEME_KEY = 'travel-buddy-theme'

function initialTheme(): Theme {
  try {
    const saved = window.localStorage.getItem(THEME_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // storage can be blocked; fall back to the system setting
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** The real API by default; run with VITE_USE_SAMPLE_DATA=true to use built-in sample data without a backend. */
function createApi(): BookingsApi {
  return import.meta.env.VITE_USE_SAMPLE_DATA === 'true' ? createFixtureApi() : createHttpApi()
}

function App() {
  const [api] = useState<BookingsApi>(createApi)
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const route = parseHash(useHash())
  const conversations = useConversations()

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      window.localStorage.setItem(THEME_KEY, theme)
    } catch {
      // not saving the choice is fine
    }
  }, [theme])

  return (
    <>
      <header className="header">
        <div className="header-inner">
          <a className="brand" href={listHref}>
            <span className="brand-mark" aria-hidden="true">✈</span>
            Travel Buddy
          </a>
          <div className="header-actions">
            <span className="pill pill-sim">Simulated environment</span>
            <button
              className="btn btn-small"
              type="button"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              {theme === 'dark' ? 'Light mode' : 'Dark mode'}
            </button>
          </div>
        </div>
      </header>
      <main className="container">
        {route.name === 'booking' ? <BookingDetail
            key={route.id}
            api={api}
            bookingId={route.id}
            conversation={conversations.get(route.id)}
            update={conversations.update}
          /> : <BookingsList api={api} />}
      </main>
      <footer className="footer">
        Everything in Travel Buddy is simulated. No real ticket will be issued.
        {(api.kind === 'sample' || api.dev) && <span> {api.label}</span>}
      </footer>
    </>
  )
}

export default App
