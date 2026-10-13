"use client";

import type { ReactNode } from "react";

export default function EmptyState({ children, className = "text-sm text-[#666]" }: { children: ReactNode; className?: string }) {
  return <p className={className}>{children}</p>;
}
