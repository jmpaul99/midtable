"use client";

import type { ReactNode } from "react";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <div className="stack" style={{ justifyItems: "center" }}>
        <i className="spinner" />
        <span>{label}…</span>
      </div>
    </div>
  );
}

export function ErrorState({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="notice error" role="alert">
      <div className="row between">
        <span>{error}</span>
        {retry && (
          <button type="button" className="secondary" onClick={retry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <div>{children}</div>}
    </div>
  );
}

export function Status({ value }: { value: string }) {
  const good = ["active", "ready", "succeeded", "complete", "completed", "locked", "running"].includes(
    value.toLowerCase(),
  );
  return (
    <span className="pill">
      <i className="dot" style={{ background: good ? "var(--brand)" : "var(--warning)" }} />
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function JsonEditor({
  label,
  value,
  onChange,
}: {
  label: string;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const serialized = JSON.stringify(value, null, 2) ?? "";
  return (
    <label>
      {label}
      <textarea
        spellCheck={false}
        defaultValue={serialized}
        key={serialized}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value));
            e.currentTarget.setAttribute("aria-invalid", "false");
          } catch {
            e.currentTarget.setAttribute("aria-invalid", "true");
          }
        }}
      />
    </label>
  );
}
