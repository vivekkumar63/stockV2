import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import { DashboardPage } from './pages/DashboardPage'
import { PortfolioPage } from './pages/PortfolioPage'
import { BacktestPage } from './pages/BacktestPage'
import { ScannerPage } from './pages/ScannerPage'
import { StrategyMatchPage } from './pages/StrategyMatchPage'
import { CombinationsPage } from './pages/CombinationsPage'
import { SpecialStrategiesPage } from './pages/SpecialStrategiesPage'
import { SectorRotationPage } from './pages/SectorRotationPage'

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
              <Route path="/scanner" element={<ScannerPage />} />
              <Route path="/strategy-match" element={<StrategyMatchPage />} />
              <Route path="/combinations" element={<CombinationsPage />} />
              <Route path="/special-strategies" element={<SpecialStrategiesPage />} />
              <Route path="/sector-rotation" element={<SectorRotationPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
