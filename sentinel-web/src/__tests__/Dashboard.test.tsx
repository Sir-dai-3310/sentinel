import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Dashboard from '../pages/Dashboard'

// Mock axios
vi.mock('axios')

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('Dashboard', () => {
  it('renders dashboard title', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    expect(screen.getByText('Security Dashboard')).toBeInTheDocument()
  })

  it('renders stat cards', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    expect(screen.getByText('Total Events')).toBeInTheDocument()
    expect(screen.getByText('Alerts')).toBeInTheDocument()
    expect(screen.getByText('Critical')).toBeInTheDocument()
    expect(screen.getByText('Accuracy')).toBeInTheDocument()
  })

  it('shows loading state initially', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    expect(screen.getAllByText('Loading...').length).toBeGreaterThan(0)
  })
})
