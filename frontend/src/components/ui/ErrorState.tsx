"use client";

export default function ErrorState({ message, onRetry, retryLabel = "Повторить" }: { message: string; onRetry: () => void; retryLabel?: string }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 border-2 border-[#ff4b26] bg-white px-4 py-3 text-sm font-bold text-[#a62910]">
      <p className="min-w-0 flex-1">{message}</p>
      <button type="button" onClick={onRetry} className="shrink-0 border-2 border-black px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[#111] hover:bg-[#ffd500]">{retryLabel}</button>
    </div>
  );
}
