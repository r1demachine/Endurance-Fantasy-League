"use client";

import type { HTMLAttributes, ReactNode } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & { children: ReactNode };

export default function Card({ children, className = "border-2 border-black bg-white", ...props }: CardProps) {
  return <div className={className} {...props}>{children}</div>;
}
