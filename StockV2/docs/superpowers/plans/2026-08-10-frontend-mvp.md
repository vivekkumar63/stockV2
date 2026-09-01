# Frontend MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-page React frontend — Dashboard (today's signals + portfolio snapshot), Portfolio (holdings + trade history + exit), Backtest (run form + results + trade detail) — against the existing StockV2 FastAPI backend at `http://localhost:8000`.

**Architecture:** Vite + React 18 + TypeScript single-page app. React Query manages server state. A thin `api/` layer (one file per domain) wraps all fetch calls with a shared `X-API-Key` header. Three page components are route-mapped via React Router; `NavBar` provides shared navigation. The backend CORS is already configured for `http://localhost:3000`, so Vite is configured to serve on that port.

**Tech Stack:** React 18, TypeScript 5, Vite 5, Tailwind CSS 3, TanStack React Query v5, React Router v6, Vitest 1, React Testing Library 14, jsdom

---

## Backend API reference (do not re-implement — already exists)

All endpoints are under `http://localhost:8000/api/v1` and require header `X-API-Key: <key>`.

| Method | Path | Returns |
|--------|------|---------|
| GET | `/signals/today` | `Signal[]` sorted by confidence desc |
| GET | `/portfolio/summary` | `{ paper_capital, total_invested, cash_available, open_positions, max_positions }` |
| GET | `/portfolio/holdings` | `Holding[]` — active positions |
| GET | `/portfolio/pnl` | `{ total_pnl, closed_trades[] }` |
| POST | `/portfolio/enter/{signal_id}` | body `{ price }` → trade record |
| POST | `/portfolio/exit/{symbol}` | body `{ price, reason }` → trade record |
| POST | `/backtest/run` | body `{ symbol, from_date, to_date }` → `BacktestResult` |
| GET | `/backtest/results` | `BacktestResult[]` |
| GET | `/backtest/results/{id}/trades` | `BacktestTrade[]` |

Signal fields: `id, symbol, strategy_name, signal_type, price_at_signal, confidence_score, suggested_stop_loss, suggested_target, holding_period_days`

Holding fields: `id, symbol, quantity, avg_buy_price, invested_value, stop_loss_price, target_1_price`

BacktestResult fields: `id, symbol, from_date, to_date, total_trades, win_rate, cagr, sharpe_ratio, max_drawdown, profit_factor`

BacktestTrade fields: `id, entry_date, entry_price, exit_date, exit_price, quantity, pnl, pnl_pct, exit_reason`

---

## File Map

```
frontend/                           NEW directory at repo root
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── tsconfig.app.json
├── .env.example
└── src/
    ├── main.tsx                    entry point
    ├── App.tsx                     router + QueryClientProvider
    ├── index.css                   Tailwind directives
    ├── test-setup.ts               jest-dom matchers
    ├── api/
    │   ├── client.ts               apiFetch base wrapper
    │   ├── signals.ts              getTodaySignals, getSignals
    │   ├── portfolio.ts            summary, holdings, pnl, enter, exit
    │   ├── backtest.ts             run, list, trades
    │   └── __tests__/
    │       ├── signals.test.ts
    │       ├── portfolio.test.ts
    │       └── backtest.test.ts
    ├── components/
    │   └── NavBar.tsx
    └── pages/
        ├── DashboardPage.tsx
        ├── PortfolioPage.tsx
        ├── BacktestPage.tsx
        └── __tests__/
            ├── DashboardPage.test.tsx
            ├── PortfolioPage.test.tsx
            └── BacktestPage.test.tsx
```

---

### Task 1: Scaffold + API Client

**Files:**
- Create: `frontend/` directory tree (via Vite scaffold)
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/signals.ts`
- Create: `frontend/src/api/portfolio.ts`
- Create: `frontend/src/api/backtest.ts`
- Create: `frontend/src/api/__tests__/signals.test.ts`
- Create: `frontend/src/api/__tests__/portfolio.test.ts`
- Create: `frontend/src/api/__tests__/backtest.test.ts`

- [ ] **Step 1: Scaffold the Vite project**

```bash
cd /c/DLP_Repos/MyRepo/StockV2
npm create vite@latest frontend -- --template react-ts
```

Expected: directory `frontend/` created with React+TS template.

- [ ] **Step 2: Install all dependencies**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend
npm install
npm install react-router-dom @tanstack/react-query
npm install -D tailwindcss autoprefixer postcss \
  vitest @vitest/coverage-v8 \
  @testing-library/react @testing-library/jest-dom @testing-library/user-event \
  jsdom
npx tailwindcss init -p
```

Expected: `node_modules/` populated, `tailwind.config.js` and `postcss.config.js` created.

- [ ] **Step 3: Write config files**

Replace `frontend/vite.config.ts` with:

```typescript
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 3000 },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

Replace `frontend/tailwind.config.js` with:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

Create `frontend/src/test-setup.ts`:

```typescript
import '@testing-library/jest-dom'
```

Create `frontend/src/index.css` (replace existing):

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

Create `frontend/.env.example`:

```
VITE_API_BASE=http://localhost:8000/api/v1
VITE_API_KEY=changeme
```

Add test scripts to `frontend/package.json` — in the `"scripts"` section add:

```json
"test": "vitest",
"test:run": "vitest run"
```

In `frontend/tsconfig.app.json`, add `"vitest/globals"` to compilerOptions types. Find the `"compilerOptions"` block and add or update:

```json
"types": ["vitest/globals"]
```

- [ ] **Step 4: Write failing API client tests**

Create `frontend/src/api/__tests__/signals.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

vi.mock('../client', () => ({ apiFetch: vi.fn() }))

import { getTodaySignals, getSignals } from '../signals'
import { apiFetch } from '../client'

describe('signals API', () => {
  it('getTodaySignals calls /signals/today', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([{ id: 1, symbol: 'TCS', signal_type: 'BUY' }])
    const result = await getTodaySignals()
    expect(apiFetch).toHaveBeenCalledWith('/signals/today')
    expect(result[0].symbol).toBe('TCS')
  })

  it('getSignals passes symbol as query param', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await getSignals({ symbol: 'TCS', signal_type: 'BUY' })
    expect(apiFetch).toHaveBeenCalledWith(expect.stringContaining('symbol=TCS'))
  })
})
```

Create `frontend/src/api/__tests__/portfolio.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

vi.mock('../client', () => ({ apiFetch: vi.fn() }))

import { getPortfolioSummary, getHoldings, enterPosition, exitPosition } from '../portfolio'
import { apiFetch } from '../client'

describe('portfolio API', () => {
  it('getPortfolioSummary calls /portfolio/summary', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ paper_capital: 500000 })
    await getPortfolioSummary()
    expect(apiFetch).toHaveBeenCalledWith('/portfolio/summary')
  })

  it('getHoldings calls /portfolio/holdings', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await getHoldings()
    expect(apiFetch).toHaveBeenCalledWith('/portfolio/holdings')
  })

  it('enterPosition calls POST /portfolio/enter/{id}', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ id: 1 })
    await enterPosition(42, 3500)
    expect(apiFetch).toHaveBeenCalledWith(
      '/portfolio/enter/42',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ price: 3500 }) }),
    )
  })

  it('exitPosition calls POST /portfolio/exit/{symbol}', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ id: 1 })
    await exitPosition('TCS', 3600, 'manual')
    expect(apiFetch).toHaveBeenCalledWith(
      '/portfolio/exit/TCS',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ price: 3600, reason: 'manual' }) }),
    )
  })
})
```

Create `frontend/src/api/__tests__/backtest.test.ts`:

```typescript
import { describe, it, expect, vi } from 'vitest'

vi.mock('../client', () => ({ apiFetch: vi.fn() }))

import { runBacktest, listBacktestResults, getBacktestTrades } from '../backtest'
import { apiFetch } from '../client'

describe('backtest API', () => {
  it('runBacktest calls POST /backtest/run', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ result_id: 1 })
    await runBacktest({ symbol: 'TCS', from_date: '2021-01-04', to_date: '2021-03-31' })
    expect(apiFetch).toHaveBeenCalledWith(
      '/backtest/run',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('listBacktestResults calls /backtest/results', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await listBacktestResults()
    expect(apiFetch).toHaveBeenCalledWith(expect.stringContaining('/backtest/results'))
  })

  it('getBacktestTrades calls /backtest/results/{id}/trades', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await getBacktestTrades(5)
    expect(apiFetch).toHaveBeenCalledWith('/backtest/results/5/trades')
  })
})
```

- [ ] **Step 5: Run tests to confirm failure**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/api/__tests__
```

Expected: `Cannot find module '../signals'` (or similar) — 9 tests failing.

- [ ] **Step 6: Create API client files**

Create `frontend/src/api/client.ts`:

```typescript
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'
const API_KEY = import.meta.env.VITE_API_KEY ?? 'changeme'

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...options.headers,
    },
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch { /* ignore parse errors */ }
    throw new Error(detail)
  }
  return res.json()
}
```

Create `frontend/src/api/signals.ts`:

```typescript
import { apiFetch } from './client'

export interface Signal {
  id: number
  symbol: string
  strategy_id: number
  strategy_name: string
  signal_date: string
  signal_type: 'BUY' | 'SELL' | 'NONE'
  price_at_signal: number
  confidence_score: number | null
  risk_score: number | null
  expected_upside_pct: number | null
  suggested_stop_loss: number | null
  suggested_target: number | null
  holding_period_days: number | null
}

export const getTodaySignals = () => apiFetch<Signal[]>('/signals/today')

export const getSignals = (params?: {
  symbol?: string
  signal_type?: string
  from_date?: string
  limit?: number
}) => {
  const q = new URLSearchParams()
  if (params?.symbol) q.set('symbol', params.symbol)
  if (params?.signal_type) q.set('signal_type', params.signal_type)
  if (params?.from_date) q.set('from_date', params.from_date)
  if (params?.limit != null) q.set('limit', String(params.limit))
  const qs = q.toString()
  return apiFetch<Signal[]>(`/signals${qs ? `?${qs}` : ''}`)
}
```

Create `frontend/src/api/portfolio.ts`:

```typescript
import { apiFetch } from './client'

export interface PortfolioSummary {
  paper_capital: number
  total_invested: number
  cash_available: number
  open_positions: number
  max_positions: number
}

export interface Holding {
  id: number
  symbol: string
  quantity: number
  avg_buy_price: number
  first_buy_date: string
  last_buy_date: string
  invested_value: number
  stop_loss_price: number | null
  target_1_price: number | null
  max_exit_date: string | null
}

export interface ClosedPnl {
  total_pnl: number
  closed_trades: ClosedTrade[]
}

export interface ClosedTrade {
  symbol: string
  trade_date: string
  quantity: number
  price: number
  buy_avg?: number
  pnl?: number
  pnl_pct?: number
}

export const getPortfolioSummary = () => apiFetch<PortfolioSummary>('/portfolio/summary')
export const getHoldings = () => apiFetch<Holding[]>('/portfolio/holdings')
export const getClosedPnl = () => apiFetch<ClosedPnl>('/portfolio/pnl')

export const enterPosition = (signalId: number, price: number) =>
  apiFetch(`/portfolio/enter/${signalId}`, {
    method: 'POST',
    body: JSON.stringify({ price }),
  })

export const exitPosition = (symbol: string, price: number, reason = 'manual') =>
  apiFetch(`/portfolio/exit/${symbol}`, {
    method: 'POST',
    body: JSON.stringify({ price, reason }),
  })
```

Create `frontend/src/api/backtest.ts`:

```typescript
import { apiFetch } from './client'

export interface BacktestRunRequest {
  symbol: string
  from_date: string
  to_date: string
  strategy_id?: number
  initial_capital?: number
}

export interface BacktestResult {
  id?: number
  result_id?: number
  symbol: string
  from_date: string
  to_date: string
  total_trades: number
  win_rate: number | null
  total_pnl?: number
  cagr: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  profit_factor: number | null
  avg_return_pct: number | null
  ran_at?: string
}

export interface BacktestTrade {
  id: number
  symbol: string
  entry_date: string
  entry_price: number
  exit_date: string
  exit_price: number
  quantity: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  holding_days: number
}

export const runBacktest = (req: BacktestRunRequest) =>
  apiFetch<BacktestResult>('/backtest/run', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const listBacktestResults = (symbol?: string, limit = 20) => {
  const q = new URLSearchParams({ limit: String(limit) })
  if (symbol) q.set('symbol', symbol)
  return apiFetch<BacktestResult[]>(`/backtest/results?${q.toString()}`)
}

export const getBacktestResult = (id: number) =>
  apiFetch<BacktestResult>(`/backtest/results/${id}`)

export const getBacktestTrades = (id: number) =>
  apiFetch<BacktestTrade[]>(`/backtest/results/${id}/trades`)
```

- [ ] **Step 7: Run tests and confirm they pass**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/api/__tests__
```

Expected: 9 passed.

- [ ] **Step 8: Commit**

```bash
cd /c/DLP_Repos/MyRepo/StockV2
git add frontend/
git commit -m "feat: frontend scaffold — Vite+React+TS, Tailwind, API client layer"
```

---

### Task 2: App Shell + Dashboard Page

**Files:**
- Create: `frontend/src/main.tsx` (replace scaffold version)
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/components/NavBar.tsx`
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/pages/__tests__/DashboardPage.test.tsx`

- [ ] **Step 1: Write failing Dashboard test**

Create `frontend/src/pages/__tests__/DashboardPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { DashboardPage } from '../DashboardPage'

vi.mock('../../api/signals', () => ({
  getTodaySignals: vi.fn().mockResolvedValue([
    {
      id: 1, symbol: 'TCS', signal_type: 'BUY', confidence_score: 0.85,
      price_at_signal: 3500, strategy_name: 'RSI Oversold',
      suggested_stop_loss: 3255, suggested_target: 4025, holding_period_days: 15,
    },
  ]),
}))
vi.mock('../../api/portfolio', () => ({
  getPortfolioSummary: vi.fn().mockResolvedValue({
    paper_capital: 500000, total_invested: 50000, cash_available: 450000,
    open_positions: 1, max_positions: 8,
  }),
  enterPosition: vi.fn().mockResolvedValue({ id: 1 }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('DashboardPage', () => {
  it('renders portfolio summary section', async () => {
    render(<DashboardPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('Paper Capital')).toBeInTheDocument())
  })

  it('renders today BUY signals with symbol', async () => {
    render(<DashboardPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('TCS')).toBeInTheDocument())
  })

  it('renders Enter button per signal', async () => {
    render(<DashboardPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Enter' })).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx
```

Expected: `Cannot find module '../DashboardPage'`

- [ ] **Step 3: Create App shell and NavBar**

Replace `frontend/src/main.tsx`:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

Create `frontend/src/App.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { DashboardPage } from './pages/DashboardPage'
import { PortfolioPage } from './pages/PortfolioPage'
import { BacktestPage } from './pages/BacktestPage'

const queryClient = new QueryClient()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50">
          <NavBar />
          <main className="max-w-7xl mx-auto p-6">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              <Route path="/backtest" element={<BacktestPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
```

Create `frontend/src/components/NavBar.tsx`:

```tsx
import { NavLink } from 'react-router-dom'

export function NavBar() {
  const link = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'text-blue-400 font-semibold' : 'hover:text-gray-300 transition-colors'
  return (
    <nav className="bg-gray-900 text-white px-6 py-3 flex gap-6 items-center shadow">
      <span className="font-bold text-lg tracking-tight">StockV2</span>
      <NavLink to="/" end className={link}>Dashboard</NavLink>
      <NavLink to="/portfolio" className={link}>Portfolio</NavLink>
      <NavLink to="/backtest" className={link}>Backtest</NavLink>
    </nav>
  )
}
```

- [ ] **Step 4: Create DashboardPage**

Create `frontend/src/pages/DashboardPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { enterPosition, getPortfolioSummary } from '../api/portfolio'
import { getTodaySignals, type Signal } from '../api/signals'

const inr = (n: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)

export function DashboardPage() {
  const qc = useQueryClient()

  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: getPortfolioSummary,
  })

  const { data: signals = [], isLoading: loadingSignals } = useQuery({
    queryKey: ['signals', 'today'],
    queryFn: getTodaySignals,
  })

  const enterMut = useMutation({
    mutationFn: ({ signalId, price }: { signalId: number; price: number }) =>
      enterPosition(signalId, price),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolio'] }),
  })

  const buySignals = signals.filter((s) => s.signal_type === 'BUY')

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {loadingSummary ? (
          <p className="col-span-4 text-gray-400">Loading…</p>
        ) : summary ? (
          <>
            <Card label="Paper Capital" value={inr(summary.paper_capital)} />
            <Card label="Invested" value={inr(summary.total_invested)} />
            <Card label="Available" value={inr(summary.cash_available)} />
            <Card label="Positions" value={`${summary.open_positions} / ${summary.max_positions}`} />
          </>
        ) : null}
      </div>

      {/* Today's BUY signals */}
      <section>
        <h2 className="text-lg font-semibold text-gray-700 mb-3">Today's BUY Signals</h2>
        {loadingSignals ? (
          <p className="text-gray-400">Loading…</p>
        ) : buySignals.length === 0 ? (
          <p className="text-gray-500 py-4">No BUY signals today.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th className="px-4 py-2">Symbol</th>
                  <th className="px-4 py-2">Strategy</th>
                  <th className="px-4 py-2">Confidence</th>
                  <th className="px-4 py-2">Price</th>
                  <th className="px-4 py-2">Stop Loss</th>
                  <th className="px-4 py-2">Target</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {buySignals.map((sig) => (
                  <SignalRow
                    key={sig.id}
                    sig={sig}
                    onEnter={() => enterMut.mutate({ signalId: sig.id, price: sig.price_at_signal })}
                    entering={enterMut.isPending}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-gray-800">{value}</p>
    </div>
  )
}

function SignalRow({ sig, onEnter, entering }: { sig: Signal; onEnter: () => void; entering: boolean }) {
  const inr = (n: number) =>
    new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)
  const conf = sig.confidence_score
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-semibold">{sig.symbol}</td>
      <td className="px-4 py-2 text-gray-500">{sig.strategy_name}</td>
      <td className="px-4 py-2">
        {conf != null ? (
          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${conf >= 0.8 ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
            {(conf * 100).toFixed(0)}%
          </span>
        ) : '—'}
      </td>
      <td className="px-4 py-2">{sig.price_at_signal != null ? inr(sig.price_at_signal) : '—'}</td>
      <td className="px-4 py-2 text-red-600">{sig.suggested_stop_loss != null ? inr(sig.suggested_stop_loss) : '—'}</td>
      <td className="px-4 py-2 text-green-600">{sig.suggested_target != null ? inr(sig.suggested_target) : '—'}</td>
      <td className="px-4 py-2">
        <button
          onClick={onEnter}
          disabled={entering}
          className="px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
        >
          Enter
        </button>
      </td>
    </tr>
  )
}
```

Note: `PortfolioPage` and `BacktestPage` will be created in Tasks 3 and 4. For now, create stub files so `App.tsx` compiles:

Create `frontend/src/pages/PortfolioPage.tsx` (stub):

```tsx
export function PortfolioPage() {
  return <div className="text-gray-400">Portfolio — coming in Task 3</div>
}
```

Create `frontend/src/pages/BacktestPage.tsx` (stub):

```tsx
export function BacktestPage() {
  return <div className="text-gray-400">Backtest — coming in Task 4</div>
}
```

- [ ] **Step 5: Run Dashboard tests**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx
```

Expected: 3 passed.

- [ ] **Step 6: Run full test suite**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run
```

Expected: all 12 tests pass (9 API + 3 Dashboard).

- [ ] **Step 7: Commit**

```bash
cd /c/DLP_Repos/MyRepo/StockV2
git add frontend/
git commit -m "feat: app shell + Dashboard — portfolio summary cards, today's BUY signals, enter position"
```

---

### Task 3: Portfolio Page

**Files:**
- Replace: `frontend/src/pages/PortfolioPage.tsx` (was stub)
- Create: `frontend/src/pages/__tests__/PortfolioPage.test.tsx`

- [ ] **Step 1: Write failing Portfolio test**

Create `frontend/src/pages/__tests__/PortfolioPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { PortfolioPage } from '../PortfolioPage'

const mockHoldings = [
  {
    id: 1, symbol: 'TCS', quantity: 10, avg_buy_price: 3500,
    first_buy_date: '2024-01-02', last_buy_date: '2024-01-02',
    invested_value: 35000, stop_loss_price: 3255, target_1_price: 4025, max_exit_date: null,
  },
]
const mockPnl = {
  total_pnl: 5000,
  closed_trades: [
    { symbol: 'INFY', trade_date: '2024-02-01', quantity: 5, price: 1600, buy_avg: 1500, pnl: 500, pnl_pct: 6.67 },
  ],
}

vi.mock('../../api/portfolio', () => ({
  getHoldings: vi.fn().mockResolvedValue(mockHoldings),
  getClosedPnl: vi.fn().mockResolvedValue(mockPnl),
  exitPosition: vi.fn().mockResolvedValue({ id: 1 }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('PortfolioPage', () => {
  it('renders open holdings with symbol', async () => {
    render(<PortfolioPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('TCS')).toBeInTheDocument())
  })

  it('renders closed P&L section', async () => {
    render(<PortfolioPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText(/Closed P&L/)).toBeInTheDocument())
  })

  it('renders closed trade row with symbol', async () => {
    render(<PortfolioPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('INFY')).toBeInTheDocument())
  })

  it('Exit button is disabled when price input is empty', async () => {
    render(<PortfolioPage />, { wrapper: Wrapper })
    await waitFor(() => screen.getByText('TCS'))
    const btn = screen.getByRole('button', { name: 'Exit' })
    expect(btn).toBeDisabled()
  })

  it('Exit button enables when price is entered', async () => {
    render(<PortfolioPage />, { wrapper: Wrapper })
    await waitFor(() => screen.getByText('TCS'))
    const input = screen.getByPlaceholderText('exit price')
    await userEvent.type(input, '3600')
    expect(screen.getByRole('button', { name: 'Exit' })).not.toBeDisabled()
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/pages/__tests__/PortfolioPage.test.tsx
```

Expected: `PortfolioPage` stub renders but assertions about TCS holdings fail — or tests pass vacuously. Either way, we are replacing the stub with the real implementation.

- [ ] **Step 3: Implement PortfolioPage**

Replace `frontend/src/pages/PortfolioPage.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { exitPosition, getClosedPnl, getHoldings, type ClosedTrade, type Holding } from '../api/portfolio'

const inr = (n: number) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)

export function PortfolioPage() {
  const qc = useQueryClient()
  const [exitPrices, setExitPrices] = useState<Record<string, string>>({})

  const { data: holdings = [], isLoading: loadingHoldings } = useQuery({
    queryKey: ['portfolio', 'holdings'],
    queryFn: getHoldings,
  })

  const { data: pnlData, isLoading: loadingPnl } = useQuery({
    queryKey: ['portfolio', 'pnl'],
    queryFn: getClosedPnl,
  })

  const exitMut = useMutation({
    mutationFn: ({ symbol, price }: { symbol: string; price: number }) =>
      exitPosition(symbol, price, 'manual'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-800">Portfolio</h1>

      {/* Open Positions */}
      <section>
        <h2 className="text-lg font-semibold text-gray-700 mb-3">Open Positions</h2>
        {loadingHoldings ? (
          <p className="text-gray-400">Loading…</p>
        ) : holdings.length === 0 ? (
          <p className="text-gray-500 py-4">No open positions.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th className="px-4 py-2">Symbol</th>
                  <th className="px-4 py-2">Qty</th>
                  <th className="px-4 py-2">Avg Price</th>
                  <th className="px-4 py-2">Invested</th>
                  <th className="px-4 py-2">Stop Loss</th>
                  <th className="px-4 py-2">Target</th>
                  <th className="px-4 py-2">Exit Price</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {holdings.map((h) => (
                  <HoldingRow
                    key={h.id}
                    holding={h}
                    exitPrice={exitPrices[h.symbol] ?? ''}
                    onPriceChange={(v) => setExitPrices((p) => ({ ...p, [h.symbol]: v }))}
                    onExit={() =>
                      exitMut.mutate({ symbol: h.symbol, price: Number(exitPrices[h.symbol]) })
                    }
                    exiting={exitMut.isPending}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Closed P&L */}
      {!loadingPnl && pnlData && (
        <section>
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Closed P&L —{' '}
            <span className={pnlData.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
              {inr(pnlData.total_pnl)}
            </span>
          </h2>
          {pnlData.closed_trades.length === 0 ? (
            <p className="text-gray-500">No closed trades yet.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-sm">
                <thead className="bg-gray-100 text-gray-600 text-left">
                  <tr>
                    <th className="px-4 py-2">Symbol</th>
                    <th className="px-4 py-2">Date</th>
                    <th className="px-4 py-2">Qty</th>
                    <th className="px-4 py-2">Sell ₹</th>
                    <th className="px-4 py-2">Buy Avg ₹</th>
                    <th className="px-4 py-2">P&L</th>
                    <th className="px-4 py-2">P&L %</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {pnlData.closed_trades.map((t, i) => (
                    <ClosedTradeRow key={i} trade={t} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

function HoldingRow({
  holding: h, exitPrice, onPriceChange, onExit, exiting,
}: {
  holding: Holding
  exitPrice: string
  onPriceChange: (v: string) => void
  onExit: () => void
  exiting: boolean
}) {
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-semibold">{h.symbol}</td>
      <td className="px-4 py-2">{h.quantity}</td>
      <td className="px-4 py-2">{inr(h.avg_buy_price)}</td>
      <td className="px-4 py-2">{inr(h.invested_value)}</td>
      <td className="px-4 py-2 text-red-600">{h.stop_loss_price != null ? inr(h.stop_loss_price) : '—'}</td>
      <td className="px-4 py-2 text-green-600">{h.target_1_price != null ? inr(h.target_1_price) : '—'}</td>
      <td className="px-4 py-2">
        <input
          type="number"
          placeholder="exit price"
          className="w-28 border border-gray-300 rounded px-2 py-1 text-xs"
          value={exitPrice}
          onChange={(e) => onPriceChange(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <button
          onClick={onExit}
          disabled={!exitPrice || exiting}
          className="px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 disabled:opacity-50"
        >
          Exit
        </button>
      </td>
    </tr>
  )
}

function ClosedTradeRow({ trade: t }: { trade: ClosedTrade }) {
  const pos = (t.pnl ?? 0) >= 0
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-semibold">{t.symbol}</td>
      <td className="px-4 py-2 text-gray-500">{t.trade_date}</td>
      <td className="px-4 py-2">{t.quantity}</td>
      <td className="px-4 py-2">{inr(t.price)}</td>
      <td className="px-4 py-2">{t.buy_avg != null ? inr(t.buy_avg) : '—'}</td>
      <td className={`px-4 py-2 font-semibold ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl != null ? inr(t.pnl) : '—'}
      </td>
      <td className={`px-4 py-2 ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl_pct != null ? `${t.pnl_pct.toFixed(2)}%` : '—'}
      </td>
    </tr>
  )
}
```

- [ ] **Step 4: Run Portfolio tests**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/pages/__tests__/PortfolioPage.test.tsx
```

Expected: 5 passed.

- [ ] **Step 5: Run full suite**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run
```

Expected: all 17 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /c/DLP_Repos/MyRepo/StockV2
git add frontend/
git commit -m "feat: PortfolioPage — open holdings with exit flow, closed P&L trade history"
```

---

### Task 4: Backtest Page + final wiring

**Files:**
- Replace: `frontend/src/pages/BacktestPage.tsx` (was stub)
- Create: `frontend/src/pages/__tests__/BacktestPage.test.tsx`

- [ ] **Step 1: Write failing Backtest test**

Create `frontend/src/pages/__tests__/BacktestPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { BacktestPage } from '../BacktestPage'

const mockResult = {
  id: 1, result_id: 1, symbol: 'TCS',
  from_date: '2021-01-04', to_date: '2021-03-31',
  total_trades: 3, win_rate: 0.67, cagr: 12.5,
  sharpe_ratio: 1.2, max_drawdown: -5.3, profit_factor: 2.1, avg_return_pct: 4.2,
}
const mockTrades = [
  {
    id: 1, symbol: 'TCS', entry_date: '2021-01-05', entry_price: 3000,
    exit_date: '2021-01-20', exit_price: 3450, quantity: 10,
    pnl: 4500, pnl_pct: 15.0, exit_reason: 'target_hit', holding_days: 15,
  },
]

vi.mock('../../api/backtest', () => ({
  runBacktest: vi.fn().mockResolvedValue(mockResult),
  listBacktestResults: vi.fn().mockResolvedValue([mockResult]),
  getBacktestTrades: vi.fn().mockResolvedValue(mockTrades),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BacktestPage', () => {
  it('renders the run form', () => {
    render(<BacktestPage />, { wrapper: Wrapper })
    expect(screen.getByPlaceholderText(/TCS/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeInTheDocument()
  })

  it('renders results table from listBacktestResults', async () => {
    render(<BacktestPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('TCS')).toBeInTheDocument())
  })

  it('shows trades when result row is clicked', async () => {
    render(<BacktestPage />, { wrapper: Wrapper })
    await waitFor(() => screen.getByText('TCS'))
    await userEvent.click(screen.getByText('TCS'))
    await waitFor(() => expect(screen.getByText('target_hit')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/pages/__tests__/BacktestPage.test.tsx
```

Expected: stub renders, but `TCS` row and `target_hit` trade assertions fail.

- [ ] **Step 3: Implement BacktestPage**

Replace `frontend/src/pages/BacktestPage.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getBacktestTrades, listBacktestResults, runBacktest,
  type BacktestResult, type BacktestTrade,
} from '../api/backtest'

export function BacktestPage() {
  const qc = useQueryClient()
  const [form, setForm] = useState({ symbol: '', from_date: '', to_date: '' })
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const { data: results = [] } = useQuery({
    queryKey: ['backtest', 'results'],
    queryFn: () => listBacktestResults(),
  })

  const { data: trades = [] } = useQuery({
    queryKey: ['backtest', 'trades', selectedId],
    queryFn: () => getBacktestTrades(selectedId!),
    enabled: selectedId != null,
  })

  const runMut = useMutation({
    mutationFn: runBacktest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backtest', 'results'] }),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    runMut.mutate(form)
  }

  const toggleRow = (id: number) => setSelectedId((prev) => (prev === id ? null : id))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Backtest</h1>

      {/* Run form */}
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-gray-200 rounded-lg p-4 flex flex-wrap gap-4 items-end shadow-sm"
      >
        <div>
          <label className="block text-xs text-gray-500 mb-1">Symbol</label>
          <input
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-28 uppercase"
            placeholder="e.g. TCS"
            value={form.symbol}
            onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value.toUpperCase() }))}
            required
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">From</label>
          <input
            type="date"
            className="border border-gray-300 rounded px-3 py-1.5 text-sm"
            value={form.from_date}
            onChange={(e) => setForm((f) => ({ ...f, from_date: e.target.value }))}
            required
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">To</label>
          <input
            type="date"
            className="border border-gray-300 rounded px-3 py-1.5 text-sm"
            value={form.to_date}
            onChange={(e) => setForm((f) => ({ ...f, to_date: e.target.value }))}
            required
          />
        </div>
        <button
          type="submit"
          disabled={runMut.isPending}
          className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {runMut.isPending ? 'Running…' : 'Run Backtest'}
        </button>
        {runMut.isError && (
          <span className="text-red-600 text-sm">{String(runMut.error)}</span>
        )}
        {runMut.isSuccess && runMut.data && (
          <span className="text-green-600 text-sm">
            Done — {runMut.data.total_trades} trades, CAGR {runMut.data.cagr?.toFixed(2)}%
          </span>
        )}
      </form>

      {/* Results table */}
      {results.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Results <span className="text-sm font-normal text-gray-400">(click row for trades)</span>
          </h2>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th className="px-4 py-2">Symbol</th>
                  <th className="px-4 py-2">From</th>
                  <th className="px-4 py-2">To</th>
                  <th className="px-4 py-2">Trades</th>
                  <th className="px-4 py-2">Win%</th>
                  <th className="px-4 py-2">CAGR</th>
                  <th className="px-4 py-2">Sharpe</th>
                  <th className="px-4 py-2">Max DD</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {results.map((r) => (
                  <ResultRow
                    key={r.id}
                    result={r}
                    selected={selectedId === r.id}
                    onClick={() => toggleRow(r.id!)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Trade detail */}
      {selectedId != null && trades.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Trades — result #{selectedId}
          </h2>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th className="px-4 py-2">Entry</th>
                  <th className="px-4 py-2">Exit</th>
                  <th className="px-4 py-2">Qty</th>
                  <th className="px-4 py-2">Entry ₹</th>
                  <th className="px-4 py-2">Exit ₹</th>
                  <th className="px-4 py-2">P&L</th>
                  <th className="px-4 py-2">P&L %</th>
                  <th className="px-4 py-2">Reason</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {trades.map((t) => (
                  <TradeRow key={t.id} trade={t} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

function ResultRow({
  result: r, selected, onClick,
}: { result: BacktestResult; selected: boolean; onClick: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={`cursor-pointer hover:bg-blue-50 transition-colors ${selected ? 'bg-blue-50' : ''}`}
    >
      <td className="px-4 py-2 font-semibold">{r.symbol}</td>
      <td className="px-4 py-2 text-gray-500">{r.from_date}</td>
      <td className="px-4 py-2 text-gray-500">{r.to_date}</td>
      <td className="px-4 py-2">{r.total_trades}</td>
      <td className="px-4 py-2">{r.win_rate != null ? `${(r.win_rate * 100).toFixed(1)}%` : '—'}</td>
      <td className={`px-4 py-2 font-semibold ${(r.cagr ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
        {r.cagr != null ? `${r.cagr.toFixed(2)}%` : '—'}
      </td>
      <td className="px-4 py-2">{r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : '—'}</td>
      <td className="px-4 py-2 text-red-600">{r.max_drawdown != null ? `${r.max_drawdown.toFixed(2)}%` : '—'}</td>
    </tr>
  )
}

function TradeRow({ trade: t }: { trade: BacktestTrade }) {
  const pos = t.pnl >= 0
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2">{t.entry_date}</td>
      <td className="px-4 py-2">{t.exit_date}</td>
      <td className="px-4 py-2">{t.quantity}</td>
      <td className="px-4 py-2">{t.entry_price.toFixed(2)}</td>
      <td className="px-4 py-2">{t.exit_price.toFixed(2)}</td>
      <td className={`px-4 py-2 font-semibold ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl.toFixed(2)}
      </td>
      <td className={`px-4 py-2 ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl_pct.toFixed(2)}%
      </td>
      <td className="px-4 py-2 text-gray-500">{t.exit_reason}</td>
    </tr>
  )
}
```

- [ ] **Step 4: Run Backtest tests**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run -- src/pages/__tests__/BacktestPage.test.tsx
```

Expected: 3 passed.

- [ ] **Step 5: Run full test suite**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run test:run
```

Expected: all 20 tests pass (9 API + 3 Dashboard + 5 Portfolio + 3 Backtest).

- [ ] **Step 6: Verify the app builds without TS errors**

```bash
cd /c/DLP_Repos/MyRepo/StockV2/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 7: Commit and tag**

```bash
cd /c/DLP_Repos/MyRepo/StockV2
git add frontend/
git commit -m "feat: BacktestPage — run form, results table, trade detail on row click"
git tag plan5-frontend-mvp
```

---

## Summary

| Task | New files | Tests |
|---|---|---|
| Scaffold + API client | `api/client.ts`, `signals.ts`, `portfolio.ts`, `backtest.ts` | 9 |
| Dashboard | `App.tsx`, `NavBar.tsx`, `DashboardPage.tsx` | 3 |
| Portfolio | `PortfolioPage.tsx` | 5 |
| Backtest | `BacktestPage.tsx` | 3 |

**To start the app after completing all tasks:**
1. `cd /c/DLP_Repos/MyRepo/StockV2/backend && uvicorn main:app --reload`
2. `cd /c/DLP_Repos/MyRepo/StockV2/frontend && npm run dev`
3. Open `http://localhost:3000`

**Environment setup:** Copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_KEY` to match the backend's `api_key` setting (default: `changeme`).
