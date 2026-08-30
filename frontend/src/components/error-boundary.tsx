import { Component, type ErrorInfo, type ReactNode } from "react";
import { ErrorState } from "@/components/ui/error-state";

interface Props {
  children: ReactNode;
  onError?: (error: Error) => void;
}
interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
    this.props.onError?.(error);
  }

  render() {
    if (this.state.error) {
      return <ErrorState error={this.state.error} />;
    }
    return this.props.children;
  }
}