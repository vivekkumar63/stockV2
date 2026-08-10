import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { PortfolioPage } from '../PortfolioPage'

vi.mock('../../api/portfolio', () => ({
  getHoldings: vi.fn().mockResolvedValue([
    {
      id: 1, symbol: 'TCS', quantity: 10, avg_buy_price: 3500,
      first_buy_date: '2024-01-02', last_buy_date: '2024-01-02',
      invested_value: 35000, stop_loss_price: 3255, target_1_price: 4025, max_exit_date: null,
    },
  ]),
  getClosedPnl: vi.fn().mockResolvedValue({
    total_pnl: 5000,
    closed_trades: [
      { symbol: 'INFY', trade_date: '2024-02-01', quantity: 5, price: 1600, buy_avg: 1500, pnl: 500, pnl_pct: 6.67 },
    ],
  }),
  exitPosition: vi.fn().mockResolvedValue({ id: 1 }),
}))

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('PortfolioPage', () => {
  it('renders open holdings with symbol', async () => {
    render(<PortfolioPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByText('TCS')).toBeInTheDocument())
  })

  it('renders closed P&L section', async () => {
    render(<PortfolioPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByText(/Closed P&L/)).toBeInTheDocument())
  })

  it('renders closed trade row with symbol', async () => {
    render(<PortfolioPage />, { wrapper: makeWrapper() })
    await waitFor(() => expect(screen.getByText('INFY')).toBeInTheDocument())
  })

  it('Exit button is disabled when price input is empty', async () => {
    render(<PortfolioPage />, { wrapper: makeWrapper() })
    await waitFor(() => screen.getByText('TCS'))
    const btn = screen.getByRole('button', { name: /Exit TCS/i })
    expect(btn).toBeDisabled()
  })

  it('Exit button enables when price is entered', async () => {
    render(<PortfolioPage />, { wrapper: makeWrapper() })
    await waitFor(() => screen.getByText('TCS'))
    const input = screen.getByPlaceholderText('exit price')
    await userEvent.type(input, '3600')
    expect(screen.getByRole('button', { name: /Exit TCS/i })).not.toBeDisabled()
  })
})
