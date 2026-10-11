# 🏆 Endurance Fantasy League

> **Преврати свои тренировки в увлекательную игру.**
> Геймифицированная платформа для спортсменов на выносливость: Strava, Garmin и Wahoo
> превращаются в XP, уровни, сезоны и соревнования с друзьями.

**Версия:** 5.3 «Ночная газета» · **Сезоны:** Rose → Peony 🌸 
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

- 🔐 **Личный кабинет** — регистрация/вход (PBKDF2-SHA256 с постепенным обновлением хешей, JWT на 24 часа с серверным отзывом), у каждого атлета свой ключ Intervals.icu (шифрование Fernet)
- 🔄 **Синхронизация** — тренировки и сон из Intervals.icu (агрегатор Strava/Garmin/Wahoo); сон «доливается» на старые тренировки при повторном синке, XP пересчитывается по всей истории
- 🧮 **XP v6** — аддитивная система нагрузки, регулярности, качества, недельной цели, восстановления и квестов
- 🏆 **Рейтинги** — Global открыт без логина (дашборд-витрина), Friends — только для друзей
- 👥 **Друзья и социальные фичи** — поиск атлетов, заявки с взаимным автопринятием, живые уведомления (SSE + брокер Redis/in-memory), публичные профили `/u/{username}` со статистикой, графиком XP и пагинацией тренировок (20 + «Load more»)
- 🌸 **Сезоны** — 10 цветков с цветом и номером сезона; демо-ротация 3 сек, боевой режим — смена раз в месяц
- 🌙 **Тёмная тема** — «ночная газета»: глубокий индиго + светлые рамки; переключатель на главной
- 🎮 **Пасхалка** — на главной: ↑ ↓ ← → (или WASD / цыфв / тапы) → 🏃💨 бежит через экран
- 📱 **Мобильная версия** — нижняя навигация, тапы, safe-area, плавающий тултип графика

---

## 🧮 XP v6 «Additive»: формула и слои

**XP складывается из независимых источников, а не перемножается:**


Total XP = Legacy offset
         + Σ Load XP за день        (убывающая отдача)
         + Σ Consistency +30/день   (кап 5 дней/неделю)
         + Σ Quality +15/+15        (кап 30/неделю)
         + Weekly goal 0…120        (персональная норма)
         + Recovery 0…10            (sleep score)
         + Quests и достижения

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

`backend/.env` (ключевые настройки):
```
DATABASE_URL=postgresql://user:pass@host:5432/fantasy
JWT_SECRET=replace-with-at-least-32-random-characters
ENCRYPTION_KEY=your-fernet-key
REDIS_URL=redis://localhost:6379/0   # опционально; рекомендуется для общего rate-limit storage
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://endurance-fantasy-league.vercel.app
XP_ENGINE=v6
XP_QUESTS_ACTIVATION_DATE=2026-10-12
```
Регистрация ограничена 5 попытками в час на IP, вход — 5 попытками в минуту на IP; sync — 3 запроса в минуту, подключение Intervals — 5 в час, запросы в друзья — 10 в час, пауза — 10 в час. Без `REDIS_URL` лимиты хранятся в памяти отдельного процесса; при нескольких backend workers используй Redis.

Для корректного определения IP за Render настрой `FORWARDED_ALLOW_IPS=*` **только если весь публичный трафик гарантированно проходит через load balancer Render** (web-service порт не должен быть доступен напрямую). В локальной среде `backend/start.sh` по умолчанию доверяет только `127.0.0.1`. В Render Start Command установи `bash backend/start.sh` (если Root Directory = корень репозитория) или `bash start.sh` (если Root Directory = `backend`). Скрипт запускает Uvicorn с `--proxy-headers` и явно заданным `--forwarded-allow-ips`. Если приложение разворачивается за другим прокси или имеет прямой доступ к порту, укажи конкретные доверенные IP/CIDR, не используй `*`.

Новые регистрации и вход ограничивают пароль 128 символами. Старые PBKDF2-хеши формата `salt:digest` проверяются с прежними 120 000 итерациями и автоматически повышаются до 600 000 при успешном входе. Выход через `POST /api/auth/logout` повышает `token_version` и отзывает все текущие access-токены пользователя. `XP_QUESTS_ACTIVATION_DATE` задаёт границу начисления новых квестов и должна быть согласована между окружениями.

### P0: персональные данные и резервное копирование

- Профили требуют Bearer-токен. Настройка `profile_visibility`: `authenticated` (сводная статистика после входа), `friends` (сводная статистика для принятых друзей), `private` (только владелец). Настройка `activity_visibility`: `friends` или `private`. Детали тренировок и история пульса доступны владельцу либо принятым друзьям при разрешённой видимости.
- Новая регистрация требует явного согласия с политикой обработки данных. Существующие аккаунты должны принять актуальную версию в разделе Profile → Privacy & data; пока актуального согласия нет, новые подключения и синхронизация блокируются.
- `DELETE /api/intervals/disconnect` отвязывает ключ и удаляет импортированные тренировки, wellness, XP-события, недельные сводки и историю членства в лигах; аккаунт и друзья сохраняются.
- `DELETE /api/account` удаляет аккаунт и связанные персональные записи. Это необратимо.
- Автоматическая синхронизация не удаляет тренировки, отсутствующие в окне ответа Intervals. Старые тренировки сохраняются; автоматический prune отключён, потому что обычный sync получает ограниченную историю.

#### Еженедельные зашифрованные бэкапы PostgreSQL

Workflow `.github/workflows/postgres-backup.yml` запускается каждый понедельник в 02:17 UTC и вручную через Actions → Weekly encrypted PostgreSQL backup → Run workflow. Он выполняет `pg_dump`, сжимает дамп, шифрует его через `age` и отправляет только зашифрованный файл в приватное S3-совместимое хранилище. Дампы не сохраняются в GitHub Actions artifacts, поскольку репозиторий публичный.

Перед включением workflow настрой следующие GitHub Actions **Secrets**:

- `BACKUP_DATABASE_URL` — отдельная переменная с URL production PostgreSQL Render.
- `BACKUP_S3_ENDPOINT` — endpoint приватного S3/R2-хранилища.
- `BACKUP_S3_BUCKET` — имя приватного бакета.
- `BACKUP_AWS_REGION` — AWS region либо `auto` для R2.
- `BACKUP_AWS_ACCESS_KEY_ID` и `BACKUP_AWS_SECRET_ACCESS_KEY` — отдельные учётные данные с минимальными правами на запись в backup-префикс.
- `BACKUP_AGE_RECIPIENT` — публичный recipient-ключ `age`. **Приватную identity нужно хранить отдельно от бакета и репозитория**, иначе нельзя будет гарантировать конфиденциальность резервных копий.

В бакете настрой lifecycle retention (например, 90 дней) и по возможности запрети публичный доступ и удаление объектов backup-учётной записью. После настройки запусти workflow вручную и убедись, что зашифрованный файл появился в бакете. Проверяй восстановление регулярно на отдельной пустой базе с помощью `scripts/restore-postgres-backup.sh`.

Workflow — только механизм копирования. До тестового сезона отдельно проверь в панели Render фактический тариф PostgreSQL, срок жизни базы, доступные нативные бэкапы и то, что сервис не будет удалён автоматически. Код репозитория не может определить активный тариф Render.

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
