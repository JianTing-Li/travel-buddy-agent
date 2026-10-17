/** App shell: header, theme toggle, routing between the bookings list and one booking. Owner: Jian. */
import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { BookingDetail } from '../features/booking/BookingDetail.tsx'
import { BookingsList } from '../features/booking/BookingsList.tsx'
import type { BookingsApi } from './dataSource.ts'
import { useConversations } from './conversations.ts'
import { createFixtureApi } from './fixtures.ts'
import { createHttpApi, SESSION_RESET_EVENT } from './httpApi.ts'
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
  // When the server restarts (or a free server wakes up), this tab gets a fresh session: clear what the old one
  // showed and reload the page's data, so the screen and Travel Buddy agree again.
  const [resets, setResets] = useState(0)
  const { clear } = conversations
  useEffect(() => {
    const onReset = () => {
      clear()
      setResets((n) => n + 1)
    }
    window.addEventListener(SESSION_RESET_EVENT, onReset)
    return () => window.removeEventListener(SESSION_RESET_EVENT, onReset)
  }, [clear])

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
                <WrenchIcon />
                Dev
                <span className="switch-track" aria-hidden="true"><span className="switch-knob" /></span>
              </button>
            )}
            {/* Always shown, also in demo mode: nobody should mistake this for a real airline system. */}
            <span className="pill pill-sim">Simulated</span>
            <button
              className="icon-btn"
              type="button"
              onClick={() => switchTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
            </button>
          </div>
        </div>
      </header>
      <main className="container">
        {resets > 0 && (
          <div className="restart-notice" role="status">
            <p>The server restarted, so your session started fresh and earlier chats were cleared. Please send your
              last message again.</p>
            <button className="btn btn-small" type="button" onClick={() => setResets(0)}>OK</button>
          </div>
        )}
        {route.name === 'booking' ? <BookingDetail
            key={`${route.id}:${resets}`}
            api={api}
            bookingId={route.id}
            conversation={conversations.get(route.id)}
            update={conversations.update}
          /> : <BookingsList key={resets} api={api} onReset={conversations.clear} />}
      </main>
      {/* The header's "Simulated" badge says it for the whole app; the footer only helps developers. */}
      {(api.kind === 'sample' || api.dev) && <footer className="footer">{api.label}</footer>}
    </>
  )
}

/** The theme button shows where it takes you: a moon in light mode, a sun in dark mode. */
function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  )
}

function WrenchIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9l-3.8 3.8z" />
    </svg>
  )
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

export default App
