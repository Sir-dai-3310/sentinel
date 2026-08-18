import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Shield, Activity, FileText, Settings } from 'lucide-react'
import LanguageSwitcher from './LanguageSwitcher'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const { t } = useTranslation()

  const navItems = [
    { path: '/', icon: Activity, label: t('nav.dashboard') },
    { path: '/analysis', icon: Shield, label: t('nav.analysis') },
    { path: '/rules', icon: FileText, label: t('nav.rules') },
    { path: '/settings', icon: Settings, label: t('nav.settings') },
  ]

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Shield className="w-8 h-8 text-primary-500" />
              <h1 className="text-2xl font-bold">Sentinel</h1>
              <span className="text-sm text-gray-400">AI Security Platform</span>
            </div>
            <div className="flex items-center space-x-4">
              <nav className="flex space-x-1">
                {navItems.map((item) => {
                  const Icon = item.icon
                  const isActive = location.pathname === item.path
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors ${
                        isActive
                          ? 'bg-primary-600 text-white'
                          : 'text-gray-300 hover:bg-gray-700'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      <span>{item.label}</span>
                    </Link>
                  )
                })}
              </nav>
              <LanguageSwitcher />
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="container mx-auto px-4 py-8">{children}</main>

      {/* Footer */}
      <footer className="bg-gray-800 border-t border-gray-700 mt-auto">
        <div className="container mx-auto px-4 py-6 text-center text-gray-400 text-sm">
          <p>Sentinel v1.0 - Open Source AI Security Platform</p>
        </div>
      </footer>
    </div>
  )
}
