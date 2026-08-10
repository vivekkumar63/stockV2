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
    await waitFor(() => expect(screen.getByRole('button', { name: 'Enter position for TCS' })).toBeInTheDocument())
  })
})
