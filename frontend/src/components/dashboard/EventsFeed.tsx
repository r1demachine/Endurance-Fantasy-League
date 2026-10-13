import EmptyState from "@/components/ui/EmptyState";

function EventsFeed({ events }: { events: any[] }) {
  const typeIcons: Record<string, string> = {
    consistency: "📅", quality_hard: "⚡", quality_long: "🏃",
    weekly_goal: "🎯", recovery: "😴", quest: "🏆", achievement: "⭐",
  };
  return (
    <div className="border-b-2 border-black bg-white p-4 md:p-6">
      <h3 className="font-display uppercase text-xl md:text-2xl mb-4">XP-события недели</h3>
      {events.length === 0 ? <EmptyState className="text-sm text-[#666]">За эту неделю XP-событий нет.</EmptyState> : (
        <div className="space-y-2">
          {events.map((e) => (
            <div key={e.id} className="flex items-center gap-3 p-2 border border-black/10 hover:bg-black/5 transition-colors">
              <span className="text-xl shrink-0">{typeIcons[e.type] || "✨"}</span>
              <div className="flex-1 min-w-0">
                <p className="font-bold uppercase text-sm truncate">{e.title}</p>
                <p className="text-[9px] font-bold tracking-widest uppercase text-[#666]">{e.date}</p>
              </div>
              <span className="font-display text-lg text-[#16a34a] shrink-0">+{e.amount}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
