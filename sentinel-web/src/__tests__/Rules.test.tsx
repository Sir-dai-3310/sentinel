import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import Rules from '../pages/Rules'

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
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{children}</BrowserRouter>
    </QueryClientProvider>
  )
}

describe('Rules', () => {
  it('renders rules page title', () => {
    render(<Rules />, { wrapper: createWrapper() })
    expect(screen.getByText('Sigma Rules')).toBeInTheDocument()
  })

  it('renders new rule button', () => {
    render(<Rules />, { wrapper: createWrapper() })
    expect(screen.getByText('New Rule')).toBeInTheDocument()
  })

  it('renders reload button', () => {
    render(<Rules />, { wrapper: createWrapper() })
    expect(screen.getByText('Reload')).toBeInTheDocument()
  })
})
