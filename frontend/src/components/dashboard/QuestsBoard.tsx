import Card from "@/components/ui/Card";

export default function QuestsBoard({ quests }: { quests: any[] }) {
  if (!quests?.length) return null;
  return (
    <div className="border-b-2 border-black bg-white p-4 md:p-6">
      <h3 className="font-display uppercase text-xl md:text-2xl mb-4">Достижения</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {quests.map((q) => (
          <Card
            key={q.slug}
            className={`p-3 border-2 ${
              q.status === "earned"
                ? "border-[#16a34a] bg-[#16a34a]/10"
                : q.status === "unavailable"
                ? "border-black/10 bg-black/5 opacity-60"
                : "border-black/20"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="font-bold uppercase text-sm truncate">
                {q.status === "earned" ? "⭐" : q.status === "unavailable" ? "🔒" : "🏆"} {q.title}
              </p>
              <span className="font-display text-[#16a34a] shrink-0">+{q.reward}</span>
            </div>
            <p className="text-[9px] font-bold tracking-widest uppercase text-[#666] mt-1">{q.desc}</p>
            {q.status === "earned" && q.earned_at && (
              <p className="text-[9px] text-[#16a34a] mt-1">получено {q.earned_at}</p>
            )}
            {q.status === "unavailable" && (
              <p className="text-[9px] text-[#999] mt-1">данные ещё не синхронизируются</p>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
