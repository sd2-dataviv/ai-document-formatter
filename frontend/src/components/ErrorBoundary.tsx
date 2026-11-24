import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Last line of defence: a render crash shows a recovery screen instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="grid h-full place-items-center bg-slate-50 p-6 dark:bg-slate-950">
        <div className="card max-w-md p-8 text-center">
          <div className="mx-auto grid size-12 place-items-center rounded-full bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-400">
            <AlertTriangle className="size-6" />
          </div>
          <h1 className="ink-strong mt-4 text-lg font-semibold">Something went wrong</h1>
          <p className="ink-muted mt-2 text-sm">
            The page hit an unexpected error. Your documents are safe on the server, and any running formatting job
            continues in the background.
          </p>
          <pre className="mt-4 max-h-32 overflow-auto ink-muted rounded-lg bg-slate-50 p-3 text-left text-xs dark:bg-slate-950">
            {this.state.error.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <RotateCcw className="size-4" /> Reload
          </button>
        </div>
      </div>
    );
  }
}
