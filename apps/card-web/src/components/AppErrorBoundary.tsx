import { Component, type ErrorInfo, type ReactNode } from "react";

import { TenantNotFound } from "./TenantNotFound";

export class AppErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Card renderer failed", error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return <TenantNotFound kind="runtime" onRetry={() => window.location.reload()} />;
    }
    return this.props.children;
  }
}
