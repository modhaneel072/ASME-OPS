import { Component, type ErrorInfo, type ReactNode } from 'react'
import { errorMessage } from '@/api/client'
import { Button, InlineAlert } from '@/ui'

interface Props {
  children: ReactNode
  fallbackTitle?: string
}

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ASME Ops route error', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 'var(--space-6)', maxWidth: 640 }}>
          <InlineAlert
            tone="danger"
            title={this.props.fallbackTitle ?? 'This page could not be displayed'}
            actions={
              <>
                <Button size="sm" onClick={() => this.setState({ error: null })}>
                  Try again
                </Button>
                <Button size="sm" variant="ghost" onClick={() => window.location.reload()}>
                  Reload
                </Button>
              </>
            }
          >
            {errorMessage(this.state.error)}
          </InlineAlert>
        </div>
      )
    }
    return this.props.children
  }
}
