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
