# 🏆 Endurance Fantasy League

> **Преврати свои тренировки в увлекательную игру.**
> Геймифицированная платформа для спортсменов на выносливость: Strava, Garmin и Wahoo
> превращаются в XP, уровни, сезоны и соревнования с друзьями.

**Версия:** 5.3 «Ночная газета» · **Сезоны:** Rose → Peony 🌸 · **Пасхалка:** ↑↓←→ 🏃
**Прод:** https://endurance-fantasy-league.vercel.app (Vercel + Render)

---

## 📸 Скриншоты

| 🏠 Главная (свет) | 📊 Дашборд |
| :---: | :---: |
| ![home](screenshots/01-home-light.png) | ![dashboard](screenshots/02-dashboard-light.png) |

| 🌙 Тёмная тема | 👀 Публичный профиль |
| :---: | :---: |
| ![dark](screenshots/03-dashboard-dark.png) | ![public](screenshots/04-public-profile.png) |

| 🔌 Профиль и Social | 📱 Мобилка |
| :---: | :---: |
| ![profile](screenshots/05-profile-social.png) | ![mobile](screenshots/06-mobile.png) |

---

## ✨ Что внутри (v5.3)

- 🔐 **Личный кабинет** — регистрация/вход (PBKDF2 + JWT 7 дней), у каждого атлета свой ключ Intervals.icu (шифрование Fernet)
- 🔄 **Синхронизация** — тренировки и сон из Intervals.icu (агрегатор Strava/Garmin/Wahoo); сон «доливается» на старые тренировки при повторном синке, XP пересчитывается по всей истории
- 🧮 **Честная XP-формула** — `base × sleep × intensity × streak`; Activity Card объясняет каждое слагаемое
- 🏆 **Рейтинги** — Global открыт без логина (дашборд-витрина), Friends — только для друзей
- 👥 **Друзья и социальные фичи** — поиск атлетов, заявки с взаимным автопринятием, живые уведомления (SSE + брокер Redis/in-memory), публичные профили `/u/{username}` со статистикой, графиком XP и пагинацией тренировок (20 + «Load more»)
- 🌸 **Сезоны** — 10 цветков с цветом и номером сезона; демо-ротация 3 сек, боевой режим — смена раз в месяц
- 🌙 **Тёмная тема** — «ночная газета»: глубокий индиго + светлые рамки; переключатель на главной
- 🎮 **Пасхалка** — на главной: ↑ ↓ ← → (или WASD / цыфв / тапы) → 🏃💨 бежит через экран
- 📱 **Мобильная версия** — нижняя навигация, тапы, safe-area, плавающий тултип графика

---

## 🧮 «Секретный соус»: формула XP

**XP = baseXP × sleepMult × intensityMult × streakMult**

1. **baseXP** — по длительности: бег / велосипед / плавание **25 XP/ч**, остальное **15 XP/ч** (пропорционально минутам)
2. **sleepMult** ×1.0–×2.0 — плавно: 0ч → ×1.0, 8ч → ×2.0, далее циклически к ×1.0; нет данных → ×1.0
3. **intensityMult** — категории LOW ≤ 0.55 / MEDIUM 0.56–0.75 / HIGH ≥ 0.76 (+ UNKNOWN без штрафа):
   - HIGH: ×1.5 → ×1.0 → ×0.5 по календарным дням подряд (анти-фарм), после 3-го — сброс; MEDIUM/LOW или пропуск прерывают
   - MEDIUM: ×1.5, с 4-го дня подряд ×1.3 до первой HIGH
   - LOW: ×1.2 — восстановительный день
   - у каждой тренировки **своя** интенсивность; цепочка дня считается по максимуму
4. **streakMult** — стрик тренировочных дней: ×2.0 при дисциплине (1 пропуск прощается), ×1.5 после 2 пропусков, ×1.0 после 3+; повторный пропуск во время восстановления → жёсткий сброс

Округление единое (2 знака). Пересчёт всей истории — при каждой синхронизации.

---

## 🛠 Технологический стек

| Слой | Технологии |
| :--- | :--- |
| **Frontend** | Next.js (App Router), TypeScript, Tailwind CSS, Framer Motion, Recharts |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy, PyJWT, cryptography, HTTPX |
| **База данных** | PostgreSQL + авто-миграция при старте; Redis опционально (fallback — in-memory брокер) |
| **Deploy** | Vercel (frontend) + Render (backend) |
| **Внешнее API** | Intervals.icu (агрегатор Strava / Garmin / Wahoo) |

---

## 🚀 Быстрый старт (локально)

**Бэкенд** — окно 1:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

**Фронтенд** — окно 2:

```powershell
cd frontend
npm run dev
```

→ Сайт: `http://localhost:3000` · Swagger: `http://localhost:8000/docs`

### Переменные окружения

`backend/.env`:
```
DATABASE_URL=postgresql://user:pass@host:5432/fantasy
SECRET_KEY=change-me
REDIS_URL=redis://localhost:6379/0   # опционально
```

`frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 🗂 Структура

```
backend/app/
  routers/    auth · sync · friends · notifications · intervals_key · admin
  services/   xp.py (математика XP + автотесты) · intervals.py · notifications.py
  broker.py   Redis pub/sub / in-memory fallback (живые уведомления)
  models.py   User · Activity · Wellness · Friendship · Notification
frontend/src/
  app/        / · /login · /dashboard · /profile · /u/[username]
  components/ ActivityCard · XpTooltip · SocialHub · ConnectSources ·
              NotificationBell · KonamiRunner · DreamDust · Header
  lib/        auth · apiCache · notifications · seasons · theme
```

---

## 📜 История версий

| Версия | Главное |
| :--- | :--- |
| v1.0 | MVP: синк Intervals, XP, дашборд, тултипы |
| v3.x | Dream × BRUT-дизайн, кэш, анимации, мобильная шапка |
| v4.x | Личный кабинет, per-user Intervals, друзья, живые уведомления |
| v5.0 | Новая XP-система (длительность/сон/интенсивность/стрик), лидерборды |
| v5.1–5.2 | Публичные профили, плавающий тултип, пасхалка-раннер, живые сезоны |
| v5.3 | Тёмная тема «ночная газета», полировка UX |

---

## 🎮 Пасхалка

Главная страница → введи **↑ ↓ ← →** (или `W S A D`, или тапай по стрелкам) —
и спринтер 🏃💨 пробежит через весь экран. Стрелки в ленте подсвечивают прогресс комбо.

---

*We don't follow chaos. We set the plan.* ⚡