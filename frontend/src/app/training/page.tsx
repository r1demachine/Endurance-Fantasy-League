export default function TrainingPage() {
  return (
    <main className="min-h-screen bg-[#f4f4f0] px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-8">
      <div className="mx-auto min-h-[60vh] max-w-[1400px] border-2 border-t-0 border-black bg-white">
        <header className="border-b-2 border-black bg-[#ffd500] px-5 py-6 md:px-8">
          <p className="font-display text-4xl uppercase leading-none md:text-6xl">Тренировки.</p>
          <p className="mt-3 max-w-2xl text-sm text-black/70">Здесь будут тренировки по неделям, графики XP Dynamics и сезонная статистика, а также синхронизация источников и загрузка файлов.</p>
        </header>
        <section className="p-5 md:p-8">
          <p className="font-display text-2xl uppercase">Раздел готовится</p>
          <p className="mt-2 text-sm text-[#666]">Список тренировок, графики и источники данных появятся на следующем этапе обновления интерфейса.</p>
        </section>
      </div>
    </main>
  );
}
