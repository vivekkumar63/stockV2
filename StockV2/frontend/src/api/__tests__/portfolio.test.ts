import { describe, it, expect, vi } from 'vitest'

vi.mock('../client', () => ({ apiFetch: vi.fn() }))

import { getPortfolioSummary, getHoldings, getClosedPnl, enterPosition, exitPosition } from '../portfolio'
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

  it('getClosedPnl calls /portfolio/pnl', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ total_pnl: 0, closed_trades: [] })
    await getClosedPnl()
    expect(apiFetch).toHaveBeenCalledWith('/portfolio/pnl')
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
