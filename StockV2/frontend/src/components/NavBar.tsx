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
