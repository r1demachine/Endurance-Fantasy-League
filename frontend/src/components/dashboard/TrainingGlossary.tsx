"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpen, Search, X } from "lucide-react";

type GlossaryTermKey = "TSS" | "EST" | "qualifying-day" | "manual-coefficient" | "upload-coefficient" | "daily-cap" | "IF" | "baseline" | "deload" | "league-score" | "XP" | "daily-bonus" | "sleep-score";

type GlossaryEntry = {
  key: GlossaryTermKey;
  term: string;
  aliases: string[];
  description: string;
  example: string;
};

const ENTRIES: GlossaryEntry[] = [
  { key: "TSS", term: "TSS — Training Stress Score", aliases: ["Training Stress Score", "нагрузка", "training stress", "стресс", "тренировочная нагрузка"], description: "Число, которое приблизительно отражает нагрузку тренировки. Чем больше TSS, тем больше расчётная нагрузка. Это не XP и не оценка того, насколько ты хорош.", example: "TSS 80 означает большую расчётную нагрузку, чем TSS 35. Сравнивать полезнее похожие тренировки и свою историю." },
  { key: "EST", term: "EST — оценочная нагрузка", aliases: ["estimated", "estimate", "оценка", "расчётная"], description: "Пометка, что нагрузка TSS рассчитана приложением приблизительно, а не получена как готовое значение от источника. Число помогает не потерять тренировку, но может быть менее точным.", example: "Если у активности нет пригодного TSS, приложение оценивает нагрузку по доступным данным." },
  { key: "qualifying-day", term: "Квалифицирующий день", aliases: ["квалификация", "день с тренировкой", "qualifying"], description: "День, в который есть хотя бы одна тренировка длительностью от 20 минут, а суммарная нагрузка за этот день достигает минимум 20 TSS. Не любая активность автоматически считается квалифицирующей.", example: "Прогулка на 20 минут с TSS ниже 20 сама по себе порог не выполняет." },
  { key: "manual-coefficient", term: "Коэффициент ручной записи", aliases: ["manual", "0.5", "половина", "ручная тренировка"], description: "Нагрузка ручной записи учитывается с коэффициентом 0,5. Это снижает риск накрутки и сохраняет более высокий вес у данных, пришедших из подключённых источников.", example: "При прочих равных ручная запись даёт для расчёта нагрузки половину исходного значения." },
  { key: "upload-coefficient", term: "Коэффициент импорта файла", aliases: ["upload", "fit", "gpx", "tcx", "0.8", "импорт"], description: "Нагрузка, пришедшая из загруженного файла FIT, GPX или TCX, учитывается с коэффициентом 0,8. Это умеренная поправка против накрутки.", example: "Расчётный вклад импорта файла составляет 80% исходной нагрузки до применения остальных правил XP." },
  { key: "daily-cap", term: "Дневной потолок TSS", aliases: ["300", "лимит нагрузки", "потолок"], description: "При расчёте XP за нагрузку учитывается не более 300 TSS за календарный день. Дополнительный TSS сверх этого значения не увеличивает XP за нагрузку этого дня.", example: "Дневные значения TSS 320 и 300 имеют одинаковый потолок для этой части расчёта XP." },
  { key: "IF", term: "IF — Intensity Factor", aliases: ["intensity factor", "интенсивность", "0.75"], description: "Относительная интенсивность тренировки по отношению к пороговой мощности или пульсу — в зависимости от доступных данных. В EFL значение IF от 0,75 может быть одним из признаков высокой интенсивности для соответствующей награды.", example: "IF 0,80 обычно означает работу интенсивнее, чем IF 0,60, если данные рассчитаны сопоставимым способом." },
  { key: "baseline", term: "Baseline — базовая нагрузка", aliases: ["база", "норма", "цель недели", "процент"], description: "Расчётный личный ориентир нагрузки, построенный на истории предыдущих недель. Он помогает оценивать текущую неделю относительно обычного объёма.", example: "Если базовая нагрузка 400 TSS, то 75% baseline — это 300 TSS." },
  { key: "deload", term: "Deload — разгрузочная неделя", aliases: ["разгрузка", "55%", "75%", "85%", "восстановление"], description: "Неделя с меньшей нагрузкой относительно личной базы. В EFL диапазон разгрузки — 55–85% baseline; условие допуска — минимум 2 из 3 предыдущих недель с нагрузкой не ниже 75% baseline.", example: "При baseline 400 TSS диапазон разгрузки составляет 220–340 TSS. Она нужна для планирования более лёгкой недели, а не для гонки за XP." },
  { key: "league-score", term: "League Score", aliases: ["лига", "рейтинг", "score", "дивизион"], description: "Оценка недельного результата для сравнения участников лиги. Это не просто сумма XP: формула учитывает выполнение цели, регулярность и качество нагрузки.", example: "Два человека с похожим XP могут получить разный League Score, если отличаются выполнением недельной цели и регулярностью." },
  { key: "XP", term: "XP — очки опыта", aliases: ["опыт", "experience points", "очки"], description: "Игровые очки, которые начисляются за нагрузку и предусмотренные системой бонусы. XP двигает игровой прогресс и уровни, но не является медицинской оценкой формы.", example: "За нагрузку тренировки и за отдельный дневной бонус могут начисляться разные части XP." },
  { key: "daily-bonus", term: "Дневной бонус +20 XP", aliases: ["45 минут", "бонус за тренировку", "activity bonus"], description: "Раз в календарный день бонус +20 XP получает одна не ручная тренировка длительностью от 45 минут. Если таких тренировок несколько, выбирается запись с самой высокой нагрузкой TSS.", example: "Две подходящие тренировки в один день не дают два дневных бонуса." },
  { key: "sleep-score", term: "Sleep score — оценка сна", aliases: ["сон", "восстановление", "readiness", "hrv"], description: "Число, которое источник сна рассчитывает на основании доступных показателей. Это отдельный показатель, не TSS и не XP; алгоритмы источников могут различаться.", example: "Оценку сна лучше смотреть вместе с длительностью сна и тем, как ты сам себя чувствуешь." },
];

function currentWeekReminderKey(): string {
  const today = new Date();
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7));
  const year = monday.getFullYear();
  const month = String(monday.getMonth() + 1).padStart(2, "0");
  const day = String(monday.getDate()).padStart(2, "0");
  return `efl-tss-reminder:${year}-${month}-${day}`;
}

export default function TrainingGlossary() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [showReminder, setShowReminder] = useState(false);
  const [reminderKey, setReminderKey] = useState("");
  const [highlightedKey, setHighlightedKey] = useState<GlossaryTermKey>("TSS");

  useEffect(() => {
    const key = currentWeekReminderKey();
    setReminderKey(key);
    try {
      setShowReminder(window.localStorage.getItem(key) !== "dismissed");
    } catch {
      setShowReminder(true);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isOpen]);

  const entries = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru-RU");
    if (!needle) return ENTRIES;
    return ENTRIES.filter((entry) => [
      entry.term, ...entry.aliases, entry.description, entry.example,
    ].join(" ").toLocaleLowerCase("ru-RU").includes(needle));
  }, [query]);

  const markReminderDismissed = () => {
    setShowReminder(false);
    try {
      if (reminderKey) window.localStorage.setItem(reminderKey, "dismissed");
    } catch {
      // The glossary remains usable when browser storage is unavailable.
    }
  };

  const openGlossary = (key?: GlossaryTermKey) => {
    if (key) {
      setHighlightedKey(key);
      const initialQuery = ENTRIES.find((entry) => entry.key === key)?.term.split(" — ")[0] ?? key;
      setQuery(initialQuery);
      markReminderDismissed();
    } else {
      setQuery("");
      setHighlightedKey("TSS");
    }
    setIsOpen(true);
  };

  return (
    <div className="min-w-0 space-y-2">
      <button
        type="button"
        onClick={() => openGlossary()}
        className="inline-flex max-w-full items-center gap-2 border-2 border-black bg-white px-3 py-2 text-xs font-black uppercase tracking-wide text-[#111] hover:bg-[#ffd500] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
      >
        <BookOpen aria-hidden="true" size={15} />
        Словарик терминов
      </button>

      {showReminder && (
        <div className="flex min-w-0 flex-wrap items-center gap-2 border border-black/20 bg-[#fff9d9] px-3 py-2 text-[#111]">
          <p className="min-w-0 flex-1 break-words text-xs"><strong>Помнишь, что такое TSS?</strong> Это оценка тренировочной нагрузки — не XP.</p>
          <button type="button" onClick={() => openGlossary("TSS")} className="border-2 border-black bg-white px-2 py-1 text-[11px] font-black hover:bg-[#ffd500]">Объяснить</button>
          <button type="button" onClick={markReminderDismissed} className="px-2 py-1 text-[11px] font-bold underline underline-offset-2 hover:text-[#5866f2]">Помню</button>
        </div>
      )}

      {isOpen && (
        <div
          className="fixed inset-0 z-[120] flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
          role="presentation"
          onMouseDown={(event) => { if (event.target === event.currentTarget) setIsOpen(false); }}
        >
          <section role="dialog" aria-modal="true" aria-labelledby="training-glossary-title" className="flex max-h-[92dvh] w-full max-w-2xl flex-col border-2 border-black bg-white text-[#111] shadow-[6px_6px_0_#111] sm:max-h-[86dvh]">
            <header className="flex items-start justify-between gap-3 border-b-2 border-black bg-[#ffd500] px-4 py-3 sm:px-5">
              <div className="min-w-0">
                <h2 id="training-glossary-title" className="break-words font-display text-xl uppercase sm:text-2xl">Словарик EFL</h2>
                <p className="mt-1 text-xs text-[#444]">Простые объяснения терминов и коэффициентов расчёта.</p>
              </div>
              <button type="button" onClick={() => setIsOpen(false)} aria-label="Закрыть словарик" className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-white"><X aria-hidden="true" size={18} /></button>
            </header>
            <div className="border-b-2 border-black p-3 sm:p-4">
              <label htmlFor="training-glossary-search" className="sr-only">Поиск по словам и объяснениям</label>
              <div className="flex min-w-0 items-center gap-2 border-2 border-black bg-white px-3">
                <Search aria-hidden="true" size={17} className="shrink-0 text-[#666]" />
                <input id="training-glossary-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ищи TSS, коэффициент, нагрузку…" className="min-w-0 flex-1 py-3 text-sm text-[#111] outline-none placeholder:text-[#777]" autoFocus />
                {query && <button type="button" onClick={() => setQuery("")} aria-label="Очистить поиск" className="shrink-0 p-1 text-[#666] hover:text-[#111]"><X aria-hidden="true" size={15} /></button>}
              </div>
              <p className="mt-2 text-[11px] text-[#666]">Поиск проверяет название, альтернативные слова и полный текст пояснения.</p>
            </div>
            <div className="min-h-0 overflow-y-auto p-3 sm:p-4">
              {entries.length === 0 ? <p className="py-8 text-center text-sm text-[#666]">Ничего не найдено. Попробуй другое слово.</p> : (
                <div className="space-y-3">
                  {entries.map((entry) => (
                    <article key={entry.key} className={`min-w-0 border-2 border-black p-3 sm:p-4 ${entry.key === highlightedKey ? "bg-[#fff9d9]" : "bg-[#f4f4f0]"}`}>
                      <h3 className="break-words font-display text-sm uppercase sm:text-base">{entry.term}</h3>
                      <p className="mt-2 break-words text-sm leading-relaxed">{entry.description}</p>
                      <p className="mt-2 break-words border-l-2 border-[#5866f2] pl-3 text-xs leading-relaxed text-[#555]"><strong>Пример:</strong> {entry.example}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>
            <footer className="border-t-2 border-black bg-[#f4f4f0] px-4 py-3 text-right">
              <button type="button" onClick={() => setIsOpen(false)} className="border-2 border-black bg-white px-4 py-2 text-xs font-black uppercase hover:bg-[#ffd500]">Закрыть</button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}
