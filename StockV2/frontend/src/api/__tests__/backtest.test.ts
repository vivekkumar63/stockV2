import { describe, it, expect, vi } from 'vitest'

vi.mock('../client', () => ({ apiFetch: vi.fn() }))

import { runBacktest, listBacktestResults, getBacktestResult, getBacktestTrades } from '../backtest'
import { apiFetch } from '../client'

describe('backtest API', () => {
  it('runBacktest calls POST /backtest/run with body', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ result_id: 1 })
    await runBacktest({ symbol: 'TCS', from_date: '2021-01-04', to_date: '2021-03-31' })
    expect(apiFetch).toHaveBeenCalledWith(
      '/backtest/run',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ symbol: 'TCS', from_date: '2021-01-04', to_date: '2021-03-31' }),
      }),
    )
  })

  it('listBacktestResults calls /backtest/results', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await listBacktestResults()
    expect(apiFetch).toHaveBeenCalledWith(expect.stringContaining('/backtest/results'))
  })

  it('getBacktestResult calls /backtest/results/{id}', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ id: 5, symbol: 'TCS' })
    await getBacktestResult(5)
    expect(apiFetch).toHaveBeenCalledWith('/backtest/results/5')
  })

  it('getBacktestTrades calls /backtest/results/{id}/trades', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await getBacktestTrades(5)
    expect(apiFetch).toHaveBeenCalledWith('/backtest/results/5/trades')
  })
})
