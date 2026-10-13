"use client";

import type { ReactNode } from "react";

export default function Label({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={`text-[9px] md:text-[10px] font-bold tracking-widest uppercase ${className}`}>{children}</p>;
}
