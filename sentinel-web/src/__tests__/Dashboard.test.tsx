import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Dashboard from '../pages/Dashboard'
import { ThemeProvider } from '../hooks/useTheme'

// Mock axios
vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => ({
        get: vi.fn().mockResolvedValue({ data: {} }),
        post: vi.fn(),
        delete: vi.fn(),
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() },
        },
      })),
    },
  }
})

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
      <ThemeProvider>{children}</ThemeProvider>
    </QueryClientProvider>
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
