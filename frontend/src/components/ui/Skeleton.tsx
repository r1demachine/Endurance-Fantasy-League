"use client";

export default function Skeleton({ rows = 3, label = "Загрузка", className = "" }: { rows?: number; label?: string; className?: string }) {
  return (
    <div role="status" aria-label={label} className={`space-y-2 ${className}`}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} aria-hidden="true" className={`h-4 animate-pulse bg-black/10 ${index === 0 ? "w-2/3" : index === rows - 1 ? "w-1/3" : "w-full"}`} />
      ))}
    </div>
  );
}
