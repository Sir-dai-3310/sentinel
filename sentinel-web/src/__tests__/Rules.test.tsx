import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import Rules from '../pages/Rules'

// Mock axios
vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>()
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => ({
        get: vi.fn().mockResolvedValue({ data: { total: 0, rules: [] } }),
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
      <BrowserRouter>{children}</BrowserRouter>
    </QueryClientProvider>
  )
}

describe('Rules', () => {
  it('renders rules page title', async () => {
    render(<Rules />, { wrapper: createWrapper() })
    expect(await screen.findByText('Sigma Rules')).toBeInTheDocument()

  })

  it('renders new rule button', async () => {
    render(<Rules />, { wrapper: createWrapper() })
    expect(await screen.findByText('New Rule')).toBeInTheDocument()
  })

  it('renders reload button', async () => {
    render(<Rules />, { wrapper: createWrapper() })
    expect(await screen.findByText('Reload')).toBeInTheDocument()
  })
})
