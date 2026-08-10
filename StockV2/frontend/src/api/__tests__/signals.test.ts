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
