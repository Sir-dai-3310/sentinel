import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Analysis from '../pages/Analysis'

// Mock useWebSocket hook
vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    isConnected: false,
    sendMessage: vi.fn(),
  }),
}))

const createWrapper = () => {
  return ({ children }: { children: React.ReactNode }) => (
    <BrowserRouter>{children}</BrowserRouter>
  )
}

describe('Analysis', () => {
  it('renders analysis page title', () => {
    render(<Analysis />, { wrapper: createWrapper() })
    expect(screen.getByText('Log Analysis')).toBeInTheDocument()
  })

  it('renders upload area', () => {
    render(<Analysis />, { wrapper: createWrapper() })
    expect(screen.getByText('Drop your log file here')).toBeInTheDocument()
  })

  it('shows disconnected status when WebSocket is not connected', () => {
    render(<Analysis />, { wrapper: createWrapper() })
    expect(screen.getByText('Disconnected')).toBeInTheDocument()
  })

  it('renders browse files button', () => {
    render(<Analysis />, { wrapper: createWrapper() })
    expect(screen.getByText('Browse Files')).toBeInTheDocument()
  })
})
