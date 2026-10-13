import { ResponsiveContainer, ComposedChart, CartesianGrid, XAxis, YAxis, Tooltip, Legend, Bar, Line } from "recharts";
import { Label, SectionTitle } from "@/components/ui";
import EmptyState from "@/components/ui/EmptyState";

export default function SeasonWeeksChart({ weeks }: { weeks: any[] }) {
  return (
    <div className="border-b-2 border-black">
      <div className="grid md:grid-cols-[200px_1fr]">
        <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#ffd500]">
          <div><p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">Сезон по неделям</p><div className="h-0.5 bg-black mt-3 mb-4" /><Label className="text-[#111]/70 block">XP и нагрузка TSS</Label></div>
          <span className="font-display text-4xl mt-auto">↗</span>
        </div>
        <div className="p-4 md:p-6 bg-white">
          <div className="md:hidden mb-4"><SectionTitle tone="yellow">Сезон по неделям</SectionTitle></div>
          {weeks.length === 0 ? <EmptyState className="text-sm text-[#666]">Пока нет недельных сводок за сезон.</EmptyState> : (
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={weeks} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#00000015" />
                  <XAxis dataKey="label" tick={{ fill: "#666", fontSize: 10 }} axisLine={{ stroke: "#000" }} tickLine={false} />
                  <YAxis yAxisId="xp" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
                  <YAxis yAxisId="load" orientation="right" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
                  <Tooltip />
                  <Legend />
                  <Bar yAxisId="xp" dataKey="total_xp" name="Итого XP" fill="#ff4b26" radius={[2, 2, 0, 0]} />
                  <Line yAxisId="load" type="monotone" dataKey="actual_load" name="Факт TSS" stroke="#5866f2" strokeWidth={2.5} dot={{ r: 3 }} />
                  <Line yAxisId="load" type="monotone" dataKey="target_load" name="Цель TSS" stroke="#16a34a" strokeWidth={2} strokeDasharray="5 4" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
