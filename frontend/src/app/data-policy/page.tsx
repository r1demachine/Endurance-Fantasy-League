import Link from "next/link";

const sections = [
  {
    title: "1. Данные аккаунта",
    body: "Храним имя пользователя, отображаемое имя, хеш пароля, настройки приватности и отметку о версии согласия с датой принятия.",
  },
  {
    title: "2. Тренировки",
    body: "После подключения Intervals.icu сохраняем название, тип, дату, длительность, расстояние, набор высоты, тренировочную нагрузку и данные о мощности, если они доступны. Это нужно для расчёта XP, статистики и рейтингов.",
  },
  {
    title: "3. Пульс и восстановление",
    body: "Можем хранить средний пульс тренировки, Sleep Score, продолжительность сна, HRV, пульс покоя и доступные показатели нагрузки/восстановления из wellness. Они используются только для предусмотренных приложением статистики и игровых расчётов.",
  },
  {
    title: "4. API-ключ Intervals.icu",
    body: "Ключ хранится в зашифрованном виде на сервере и используется для запросов к Intervals.icu от имени подключившего его пользователя. Ключ может разрешать доступ к данным и действиям в пределах предоставленных Intervals полномочий. Не подключайте ключ, если не готовы предоставить такие разрешения.",
  },
  {
    title: "5. Видимость и друзья",
    body: "Для просмотра профиля требуется вход. В зависимости от настройки видимости авторизованные пользователи могут видеть базовые данные профиля. Подробности тренировок и историю пульса видит владелец, а также принятые друзья, если это разрешено настройками владельца.",
  },
  {
    title: "6. Отключение и удаление",
    body: "«Отвязать Intervals и удалить ключ» удаляет ключ, импортированные тренировки, wellness и рассчитанные на их основе XP/сводки; аккаунт и список друзей остаются. «Удалить аккаунт и все данные» удаляет аккаунт и связанные персональные записи. Ранее выгруженные резервные копии могут сохраняться в течение срока хранения резервного хранилища и удаляются согласно его политике.",
  },
];

export default function DataPolicyPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-3 py-8 text-[#111]">
      <article className="mx-auto max-w-3xl border-2 border-black bg-[#f4f4f0]">
        <header className="border-b-2 border-black bg-[#ffd500] p-5 md:p-8">
          <p className="text-[10px] font-bold tracking-widest uppercase">Endurance Fantasy League · Policy v2026-10-11-v1</p>
          <h1 className="mt-3 font-display text-4xl uppercase leading-none md:text-5xl">Что мы храним<span className="text-[#ff4b26]">.</span></h1>
          <p className="mt-3 max-w-xl text-sm">
            Короткое объяснение данных, используемых для работы приложения. Согласие не отменяет право
            отвязать источник или удалить аккаунт.
          </p>
        </header>
        <div className="space-y-0 p-5 md:p-8">
          {sections.map((section) => (
            <section key={section.title} className="border-b border-black/20 py-4 first:pt-0 last:border-0">
              <h2 className="font-display text-xl uppercase">{section.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-[#333]">{section.body}</p>
            </section>
          ))}
          <p className="mt-5 text-xs leading-relaxed text-[#666]">
            Если ключ Intervals.icu больше не нужен, отзовите или перегенерируйте его также в настройках
            Intervals.icu. Перегенерация на стороне провайдера немедленно делает старый ключ недействительным.
            Эта страница — краткое объяснение практик приложения, а не замена полной юридической документации.
          </p>
          <Link href="/login" className="mt-6 inline-block bg-[#ff4b26] px-5 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black">
            ← Назад к аккаунту
          </Link>
        </div>
      </article>
    </main>
  );
}
