import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Analysis from './pages/Analysis'
import Rules from './pages/Rules'
import Settings from './pages/Settings'
import Login from './pages/Login'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="*"
        element={
          <Layout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/analysis" element={<Analysis />} />
              <Route path="/rules" element={<Rules />} />
              <Route path="/settings" element={<Settings />} />
              <Route
                path="*"
                element={
                  <div className="flex flex-col items-center justify-center min-h-[50vh] text-gray-400">
                    <h1 className="text-6xl font-bold text-gray-700">404</h1>
                    <p className="mt-2">Page not found</p>
                  </div>
                }
              />
            </Routes>
          </Layout>
        }
      />
    </Routes>
  )
}
