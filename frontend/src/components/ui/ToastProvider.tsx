"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { ToastPill, type ToastTone } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";

export type ToastOptions = {
  message: ReactNode;
  tone?: ToastTone;
  /** Milliseconds before auto-dismiss. `null` = until closed (always shows X). Default 4000. */
  durationMs?: number | null;
  /** Show a close button. Forced true when `durationMs` is `null`. Default false. */
  dismissible?: boolean;
};

type ToastRecord = {
  id: string;
  message: ReactNode;
  tone: ToastTone;
  durationMs: number | null;
  dismissible: boolean;
};

type ToastContextValue = {
  toast: (options: ToastOptions) => string;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

let toastId = 0;
function nextId() {
  toastId += 1;
  return `toast-${toastId}`;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (options: ToastOptions) => {
      const id = nextId();
      const durationMs = options.durationMs === undefined ? 4000 : options.durationMs;
      const dismissible = durationMs === null ? true : (options.dismissible ?? false);
      setToasts((current) => [
        ...current,
        {
          id,
          message: options.message,
          tone: options.tone ?? "success",
          durationMs,
          dismissible,
        },
      ]);
      return id;
    },
    [],
  );

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {mounted &&
        createPortal(
          <div
            className={cn(
              "pointer-events-none fixed inset-x-0 z-50 flex flex-col items-center gap-2 px-4",
              "bottom-[calc(5.5rem+env(safe-area-inset-bottom))] md:bottom-6",
            )}
            aria-live="polite"
          >
            {toasts.map((item) => (
              <ToastItem key={item.id} item={item} onDismiss={dismiss} />
            ))}
          </div>,
          document.body,
        )}
    </ToastContext.Provider>
  );
}

function ToastItem({
  item,
  onDismiss,
}: {
  item: ToastRecord;
  onDismiss: (id: string) => void;
}) {
  useEffect(() => {
    if (item.durationMs === null) return;
    const timer = window.setTimeout(() => onDismiss(item.id), item.durationMs);
    return () => window.clearTimeout(timer);
  }, [item.durationMs, item.id, onDismiss]);

  return (
    <ToastPill
      tone={item.tone}
      dismissible={item.dismissible}
      onDismiss={() => onDismiss(item.id)}
    >
      {item.message}
    </ToastPill>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
