/** App shell: header, theme toggle, routing between the bookings list and one booking. Owner: Jian. */
import { useEffect, useMemo, useState } from 'react'
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

/** Dev builds can hide the test tools for a demo; the choice is remembered in this browser. */
const DEV_TOOLS_KEY = 'travel-buddy-dev-tools'

/** On by default while developing; off by default on the deployed demo, so visitors first see the real app. */
function initialDevTools(): boolean {
  const fallback = !import.meta.env.PROD
  try {
    const saved = window.localStorage.getItem(DEV_TOOLS_KEY)
    return saved === null ? fallback : saved === 'on'
  } catch {
    return fallback
  }
}

function App() {
  const [baseApi] = useState<BookingsApi>(createApi)
  const [devTools, setDevTools] = useState<boolean>(initialDevTools)
  // With the dev tools off, the screens see no dev API, so the test tools and source labels disappear.
  const api = useMemo(() => (baseApi.dev && !devTools ? { ...baseApi, dev: undefined } : baseApi), [baseApi, devTools])
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const route = parseHash(useHash())
  const conversations = useConversations()

  // Fade the colors for a moment while the theme changes (see .theme-switching in index.css).
  const switchTheme = (next: Theme) => {
    const root = document.documentElement
    root.classList.add('theme-switching')
    setTheme(next)
    window.setTimeout(() => root.classList.remove('theme-switching'), 400)
  }

  const toggleDevTools = () => {
    setDevTools((on) => {
      try {
        window.localStorage.setItem(DEV_TOOLS_KEY, on ? 'off' : 'on')
      } catch {
        // not saving the choice is fine
      }
      return !on
    })
  }

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
            {baseApi.dev && (
              <button
                className="switch"
                type="button"
                role="switch"
                aria-checked={devTools}
                title="Dev tools: simulate delays and add test bookings"
                aria-label="Dev tools"
                onClick={toggleDevTools}
              >
                <span className="switch-icon" aria-hidden="true">🛠</span>
                Dev
                <span className="switch-track" aria-hidden="true"><span className="switch-knob" /></span>
              </button>
            )}
            {/* Always shown, also in demo mode: nobody should mistake this for a real airline system. */}
            <span className="pill pill-sim">Simulated</span>
            <button
              className="btn btn-small"
              type="button"
              onClick={() => switchTheme(theme === 'dark' ? 'light' : 'dark')}
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
          /> : <BookingsList api={api} onReset={conversations.clear} />}
      </main>
      {/* The header's "Simulated" badge says it for the whole app; the footer only helps developers. */}
      {(api.kind === 'sample' || api.dev) && <footer className="footer">{api.label}</footer>}
    </>
  )
}

export default App
