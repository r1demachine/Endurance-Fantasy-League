"use client";

import type { MouseEvent, TouchEvent } from "react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import XpTooltip from "@/components/XpTooltip";
import { Label, SectionTitle } from "@/components/ui";

type ChartPoint = any;
type XpDynamicsProps = {
  chartData: ChartPoint[];
  chartKey: number;
  isTouch: boolean;
  touchTooltipActive: boolean;
  tooltipPortal: HTMLElement | null;
  cursorY: number;
  handleChartTouchStart: (_nextState: unknown, event: TouchEvent<SVGGraphicsElement>) => void;
  handleChartTouchMove: (_nextState: unknown, event: TouchEvent<SVGGraphicsElement>) => void;
  handleChartTouchEnd: () => void;
  handleMouseMove: (event: MouseEvent<HTMLDivElement>) => void;
};

export default function XpDynamics({
  chartData, chartKey, isTouch, touchTooltipActive, tooltipPortal, cursorY,
  handleChartTouchStart, handleChartTouchMove, handleChartTouchEnd, handleMouseMove,
}: XpDynamicsProps) {
  return (
    {/* График */}
        {chartData.length > 0 && (
          <div className="border-b-2 border-black">
            <div className="grid md:grid-cols-[200px_1fr]">
              <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#f4f4f0]">
                <div>
                  <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">XP Dynamics</p>
                  <div className="h-0.5 bg-black mt-3 mb-4"></div>
                  <Label className="text-[#666] block">Last {chartData.length} workouts</Label>
                </div>
                <span className="font-display text-4xl mt-auto">↓</span>
              </div>
              <div className="p-4 md:p-6 bg-white" onMouseMove={handleMouseMove}>
                <div className="md:hidden mb-4">
                  <SectionTitle>XP Dynamics</SectionTitle>
                </div>
                <div className="h-64 w-full relative">
                  <ResponsiveContainer key={chartKey} width="100%" height="100%">
                    <AreaChart
                      data={chartData}
                      margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                      onTouchStart={isTouch ? handleChartTouchStart : undefined}
                      onTouchMove={isTouch ? handleChartTouchMove : undefined}
                      onTouchEnd={isTouch ? handleChartTouchEnd : undefined}
                    >
                      <defs>
                        <linearGradient id="xpFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#ff4b26" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#ff4b26" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#00000015" />
                      <XAxis dataKey="date" tick={{ fill: "#666", fontSize: 10 }} axisLine={{ stroke: "#000" }} tickLine={false} />
                      <YAxis tick={{ fill: "#666", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
                      <Tooltip
                        content={<XpTooltip chartData={chartData} />}
                        trigger="hover"
                        active={isTouch ? touchTooltipActive : undefined}
                        portal={tooltipPortal}
                        allowEscapeViewBox={{ x: true, y: true }}
                        wrapperStyle={{
                          position: "fixed",
                          left: "50%",
                          transform: "translateX(-50%)",
                          top: `${cursorY - 200}px`,
                          width: "calc(100% - 32px)",
                          maxWidth: "900px",
                          pointerEvents: "none",
                          zIndex: 100,
                        }}
                        cursor={
                          isTouch
                            ? touchTooltipActive
                              ? { stroke: "#5866f2", strokeWidth: 1 }
                              : false
                            : { stroke: "#5866f2", strokeWidth: 1 }
                        }
                      />
                      <Area type="monotone" dataKey="xp" stroke="#ff4b26" strokeWidth={2.5} fill="url(#xpFill)"
                        activeDot={{ r: 5, fill: "#171a38", stroke: "#ffd500", strokeWidth: 2 }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        )}
  );
}
