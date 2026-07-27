"use client";

import { useEffect, type RefObject } from "react";

/** Close a combobox when the pointer lands outside `rootRef`. */
export function useComboboxDismiss(
  rootRef: RefObject<HTMLElement | null>,
  onDismiss: () => void,
): void {
  useEffect(() => {
    function onDocPointerDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        onDismiss();
      }
    }
    document.addEventListener("mousedown", onDocPointerDown);
    return () => document.removeEventListener("mousedown", onDocPointerDown);
  }, [rootRef, onDismiss]);
}
