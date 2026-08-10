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
  runBacktest: vi.fn().mockResolvedValue({
    id: 1, result_id: 1, symbol: 'TCS',
    from_date: '2021-01-04', to_date: '2021-03-31',
    total_trades: 3, win_rate: 0.67, cagr: 12.5,
    sharpe_ratio: 1.2, max_drawdown: -5.3, profit_factor: 2.1, avg_return_pct: 4.2,
  }),
  listBacktestResults: vi.fn().mockResolvedValue([{
    id: 1, result_id: 1, symbol: 'TCS',
    from_date: '2021-01-04', to_date: '2021-03-31',
    total_trades: 3, win_rate: 0.67, cagr: 12.5,
    sharpe_ratio: 1.2, max_drawdown: -5.3, profit_factor: 2.1, avg_return_pct: 4.2,
  }]),
  getBacktestTrades: vi.fn().mockResolvedValue([{
    id: 1, symbol: 'TCS', entry_date: '2021-01-05', entry_price: 3000,
    exit_date: '2021-01-20', exit_price: 3450, quantity: 10,
    pnl: 4500, pnl_pct: 15.0, exit_reason: 'target_hit', holding_days: 15,
  }]),
}))

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BacktestPage', () => {
  it('renders the run form', () => {
    render(<BacktestPage />, { wrapper: makeWrapper() })
    expect(screen.getByPlaceholderText(/TCS/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeInTheDocument()
  })

  it('renders results table from listBacktestResults', async () => {
    render(<BacktestPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByText('TCS')).toBeInTheDocument())
  })

  it('shows trades when result row is clicked', async () => {
    render(<BacktestPage />, { wrapper: makeWrapper() })
    await waitFor(() => screen.getByText('TCS'))
    await userEvent.click(screen.getByText('TCS'))
    await waitFor(() => expect(screen.getByText('target_hit')).toBeInTheDocument())
  })
})
