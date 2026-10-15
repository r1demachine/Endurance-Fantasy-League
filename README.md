# 🏆 Endurance Fantasy League

**Тренируйся. Выполняй план. Зарабатывай XP. Соревнуйся.**

Endurance Fantasy League — веб-платформа, которая превращает тренировки на выносливость в игровую систему с уровнями, достижениями, персональными целями, недельными бонусами, рейтингами и соревнованиями с другими спортсменами.

Подключай [Intervals.icu](https://intervals.icu/), синхронизируй тренировочную историю и следи за своим прогрессом в едином интерфейсе.

<p align="center">
  <a href="https://endurance-fantasy-league.vercel.app">
    <img src="https://img.shields.io/badge/WEB_APP-Открыть_приложение-5866f2?style=for-the-badge" alt="Открыть приложение">
  </a>
  <a href="https://github.com/r1demachine/Endurance-Fantasy-League">
    <img src="https://img.shields.io/badge/GitHub-Repository-181717?style=for-the-badge&logo=github" alt="GitHub">
  </a>
</p>

<p align="center">
  <a href="https://github.com/r1demachine/Endurance-Fantasy-League/actions/workflows/frontend-checks.yml">
    <img src="https://github.com/r1demachine/Endurance-Fantasy-League/actions/workflows/frontend-checks.yml/badge.svg" alt="Frontend CI">
  </a>
  <a href="https://github.com/r1demachine/Endurance-Fantasy-League/actions/workflows/security-regressions.yml">
    <img src="https://github.com/r1demachine/Endurance-Fantasy-League/actions/workflows/security-regressions.yml/badge.svg" alt="Backend CI">
  </a>
</p>

---

## Содержание

- [Возможности](#-возможности)
- [Скриншоты](#-скриншоты)
- [Система XP v6](#-система-xp-v6)
- [Технологический стек](#-технологический-стек)
- [Архитектура проекта](#-архитектура-проекта)
- [Локальный запуск](#-локальный-запуск)
- [Переменные окружения](#-переменные-окружения)
- [Тестирование](#-тестирование)
- [Безопасность и приватность](#-безопасность-и-приватность)
- [Развёртывание](#-развёртывание)

---

## ✨ Возможности

### 🏃 Тренировки и аналитика

- **Синхронизация с Intervals.icu** — импорт тренировочной истории и доступных данных о восстановлении.
- **Поддержка разных видов спорта** — велоспорт, бег, плавание и другие активности.
- **Загрузка тренировок вручную** — импорт файлов FIT, GPX и TCX с предварительным разбором и подтверждением.
- **Аналитика нагрузки** — динамика XP, недельные сводки и график тренировочной истории.
- **Персональные параметры пульса** — настройки для анализа тренировок.
- **Повторный пересчёт XP** — обновление результатов при синхронизации или изменении исходных данных.

### 🎮 Геймификация

- XP за тренировочную нагрузку с убывающей отдачей.
- Уровни спортсмена и накопительный опыт.
- Персональные недельные цели.
- Квесты и достижения за тренировки, регулярность и восстановление.
- Бонусы за качественное выполнение индивидуального плана.
- История недельных результатов и разбивка начисленных XP по категориям.

### 🏆 Соревнования

- Общий рейтинг спортсменов.
- Дружеские отношения и социальные уведомления.
- Недельные лиги и дивизионы.
- Дуэли между спортсменами.
- Клубы для совместного участия в соревнованиях.
- Профили спортсменов с доступной статистикой и историей активности.

### 💬 Telegram-бот

При настроенном боте доступны привязка аккаунта по одноразовому коду, удобная ссылка для привязки, уведомления и загрузка поддерживаемых файлов тренировок непосредственно через Telegram.

### 🔐 Аккаунт и настройки

- Регистрация и авторизация.
- Персональное подключение Intervals.icu.
- Настройки видимости профиля и тренировок.
- Управление источниками данных.
- Согласие на обработку персональных данных.
- Отвязка Intervals.icu и удаление аккаунта.

---

## 📸 Скриншоты

### Главная страница и дашборд

<p align="center">
  <img src="screenshots/01-home-light.png" alt="Главная страница" width="49%">
  <img src="screenshots/02-dashboard-light.png" alt="Дашборд спортсмена" width="49%">
</p>

### Оформление и профили

<p align="center">
  <img src="screenshots/03-dashboard-dark.png" alt="Тёмная тема" width="49%">
  <img src="screenshots/04-public-profile.png" alt="Профиль спортсмена" width="49%">
</p>

### Социальные функции и мобильная версия

<p align="center">
  <img src="screenshots/05-profile-social.png" alt="Профиль и социальные функции" width="74%">
  <img src="screenshots/06-mobile.png" alt="Мобильная версия" width="24%">
</p>

---

## ⚡ Система XP v6

XP v6 — аддитивная система начисления опыта. Тренировочная нагрузка, недельные цели и дополнительные достижения учитываются как отдельные источники опыта.

Общая формула:

\[
\text{Total XP} =
\text{Legacy Offset}
+ \sum \text{Activity XP}
+ \sum \text{XP Events}
\]

| Источник | Правила |
|---|---|
| Тренировочная нагрузка | XP рассчитывается на основе нагрузки дня с убывающей отдачей |
| Дневной бонус | +20 XP за один подходящий день с тренировкой |
| Хороший сон | +6 XP за ночь при выполнении критерия сна |
| Недельная цель | До 120 XP в зависимости от выполнения персональной цели |
| Недельная регулярность | +50 XP за достижение пяти квалифицирующих тренировочных дней |
| Хороший сон за неделю | +35 XP за пять хороших ночей |
| Длинная тренировка | +25 XP за тренировку от двух часов |
| Дополнительная длительность | +15 XP за тренировку от трёх часов |
| Высокая интенсивность | +30 XP при выполнении условий недельного достижения |
| Станок | +15 XP за подходящую тренировку в сезон |
| Выполненная цель | +20 XP при выполнении не менее 100% недельной цели |
| Идеальная неделя | +40 XP при одновременном выполнении цели, тренировочного плана и условий сна |
| Разовые достижения | Дополнительные награды за достижения, предусмотренные системой |

Указанные награды за достижения начисляются отдельно и могут складываться с XP за тренировочную нагрузку.

### 🎯 Бонус «Идеальная неделя»

Бонус составляет **+40 XP один раз за неделю**, если одновременно:

- Выполнено не менее 100% персональной недельной цели.
- Достигнуто целевое количество квалифицирующих дней, но не более пяти.
- Есть минимум пять хороших ночей сна.

Хорошей считается ночь с продолжительностью сна не менее шести часов **или** `sleep score ≥ 60`.

Бонус за выполненную цель (+20 XP) начисляется отдельно. Оба события увеличивают общий XP, но не включаются непосредственно в расчёт League Score.

### ⚖️ League Score

Для рейтингов используется отдельная метрика, а не просто сумма XP. В текущей модели её веса распределяются так:

- **70%** — выполнение персональной цели.
- **20%** — регулярность.
- **10%** — качество тренировок.

Таким образом, общий XP отражает накопленную игровую ценность, а League Score помогает сравнивать спортсменов с разными тренировочными объёмами и персональными планами.

---

## 🛠 Технологический стек

| Компонент | Технологии |
|---|---|
| Frontend | Next.js 16 App Router, React 19, TypeScript |
| Стилизация | Tailwind CSS 4 |
| Визуализация | Recharts |
| Анимации | Framer Motion |
| Backend | Python 3.12, FastAPI |
| ORM | SQLAlchemy 2 |
| База данных | PostgreSQL |
| Валидация | Pydantic 2 |
| Авторизация | JWT |
| Защита данных | Fernet, PBKDF2-SHA256 |
| Ограничение запросов | SlowAPI, Redis при необходимости |
| Интеграции | Intervals.icu, Telegram Bot API |
| Frontend-деплой | Vercel |
| Backend-деплой | Render |
| Автоматические проверки | GitHub Actions |

---

## 🗂 Архитектура проекта

```text
Endurance-Fantasy-League/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── rate_limit.py
│   │   ├── broker.py
│   │   │
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── sync.py
│   │   │   ├── upload.py
│   │   │   ├── intervals_key.py
│   │   │   ├── friends.py
│   │   │   ├── notifications.py
│   │   │   ├── privacy.py
│   │   │   ├── telegram.py
│   │   │   ├── clubs.py
│   │   │   ├── duels.py
│   │   │   └── admin.py
│   │   │
│   │   └── services/
│   │       ├── xp.py
│   │       ├── xp_v6.py
│   │       ├── quests.py
│   │       ├── intervals.py
│   │       ├── notifications.py
│   │       └── activity_upload.py
│   │
│   ├── tests/
│   ├── requirements.txt
│   ├── .env.example
│   └── start.sh
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── tests/
│   ├── package.json
│   └── next.config.ts
│
├── screenshots/
├── docs/
├── scripts/
├── docker-compose.yml
└── README.md
```

### Основные модули

- `backend/app/services/xp_v6.py` — математические правила XP v6 и расчёт League Score.
- `backend/app/services/quests.py` — недельные квесты, достижения и execution bonuses.
- `backend/app/routers/sync.py` — синхронизация, недельные сводки и XP-события.
- `backend/app/routers/upload.py` — загрузка и обработка файлов тренировок.
- `backend/app/routers/telegram.py` — Telegram-интеграция и привязка аккаунтов.
- `backend/app/models.py` — ORM-модели.
- `frontend/src/components/dashboard/QuestsBoard.tsx` — интерфейс недельных и разовых достижений.
- `frontend/src/app/dashboard/page.tsx` — основной дашборд спортсмена.

---

## 🚀 Локальный запуск

### 1. Предварительные требования

Установи:

- Git.
- Python 3.12.
- Node.js 22 или совместимую актуальную версию.
- PostgreSQL.
- npm, который поставляется вместе с Node.js.

Redis нужен только при использовании соответствующей конфигурации брокера или общего хранилища лимитов.

### 2. Клонирование репозитория

```bash
git clone https://github.com/r1demachine/Endurance-Fantasy-League.git
cd Endurance-Fantasy-League
```

### 3. Настройка Backend

В PowerShell из корневой директории проекта:

```powershell
cd backend

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
```

Создай локальную базу данных PostgreSQL и укажи её параметры в `backend/.env`.

Сгенерировать секреты можно командами:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Эта команда генерирует значение для `JWT_SECRET`.

После установки зависимостей сгенерируй ключ шифрования:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Полученное значение используй как `ENCRYPTION_KEY`. Храни его постоянно: потеря или замена ключа может сделать ранее зашифрованные ключи Intervals.icu недоступными.

Запуск Backend:

```powershell
uvicorn app.main:app --reload --port 8000
```

При локальной разработке документация API доступна по адресу:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

В production-доменах документация API отключена настройкой приложения.

### 4. Настройка Frontend

Открой второе окно терминала:

```powershell
cd frontend

npm ci
```

Создай файл `frontend/.env.local` со следующим содержимым:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Запусти приложение:

```powershell
npm run dev
```

Локальный сайт: http://localhost:3000

Для работы регистрации и синхронизации Backend должен быть запущен, PostgreSQL должен быть доступен, а `CORS_ORIGINS` должен содержать origin локального Frontend.

---

## 🔧 Переменные окружения

Пример основных параметров Backend:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/fantasy_league

JWT_SECRET=replace_with_a_random_secret_at_least_32_characters
ENCRYPTION_KEY=replace_with_a_persistent_fernet_key

APP_ENV=development
XP_ENGINE=v6

INTERVALS_API_URL=https://intervals.icu/api/v1

CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://endurance-fantasy-league.vercel.app

REDIS_URL=

TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_BOT_USERNAME=
```

Это пример конфигурации, а не готовые секреты. Не используй демонстрационные значения в production.

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | Строка подключения к PostgreSQL |
| `JWT_SECRET` | Подпись токенов авторизации; минимум 32 символа |
| `ENCRYPTION_KEY` | Шифрование пользовательских API-ключей |
| `APP_ENV` | Окружение приложения |
| `XP_ENGINE` | Выбранный движок опыта, по умолчанию `v6` |
| `INTERVALS_API_URL` | Базовый URL Intervals.icu API |
| `CORS_ORIGINS` | Разрешённые источники браузерных запросов |
| `REDIS_URL` | Необязательное подключение к Redis |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота, если интеграция включена |
| `TELEGRAM_WEBHOOK_SECRET` | Секрет проверки Telegram webhook |
| `TELEGRAM_BOT_USERNAME` | Имя бота для формирования deep links |

Для каждого пользователя используется собственный ключ Intervals.icu. Он не должен попадать в репозиторий или обычные логи приложения.

**Важно:** не публикуй `.env`, `frontend/.env.local`, JWT-секреты, API-ключи, токен Telegram и учётные данные PostgreSQL.

---

## ✅ Тестирование

### Backend

Из директории `backend`:

```bash
python -m unittest discover -s tests -v
```

Тесты покрывают, в частности, правила XP, недельные бонусы, приватность, валидацию, синхронизацию, загрузку файлов и Telegram-интеграцию.

### Frontend

Из директории `frontend`:

```bash
npm test
```

Проверка типов:

```bash
npx tsc --noEmit
```

Production-сборка:

```bash
npm run build
```

Линтер:

```bash
npm run lint
```

В GitHub Actions frontend-проверки включают тесты, проверку типов, необходимые проверки UI и production build. Backend-регрессии запускаются отдельным workflow.

---

## 🔐 Безопасность и приватность

Платформа работает с пользовательскими тренировочными данными, поэтому приватность учитывается в API и настройках аккаунта.

- Авторизованные маршруты защищаются пользовательской аутентификацией.
- Ключи Intervals.icu хранятся в зашифрованном виде.
- Пароли хешируются с использованием PBKDF2-SHA256 и постепенно обновляются при успешной авторизации.
- Для чувствительных операций применяются ограничения частоты запросов и валидация входных данных.
- Настройки видимости профиля позволяют ограничивать доступ к статистике.
- Детали тренировок доступны с учётом прав владельца, отношений дружбы и выбранных настроек приватности.
- Для регистрации требуется согласие с политикой обработки данных.
- Предусмотрены отвязка источника данных и удаление аккаунта вместе со связанными персональными записями.

### Резервное копирование

В репозитории предусмотрен GitHub Actions workflow для зашифрованных резервных копий PostgreSQL.

Для его работы необходимо отдельно настроить GitHub Actions Secrets, приватное S3-совместимое хранилище и ключи шифрования. После настройки следует проверить ручной запуск workflow и восстановление копии на отдельной тестовой базе.

Фактический тариф и срок жизни production-базы PostgreSQL зависят от конфигурации Render и проверяются в панели провайдера.

---

## ☁️ Развёртывание

Проект разделён на два сервиса:

| Сервис | Платформа | Назначение |
|---|---|---|
| Frontend | [Vercel](https://vercel.com/) | Next.js-приложение |
| Backend | [Render](https://render.com/) | FastAPI и доступ к PostgreSQL |

Production-приложение:

**https://endurance-fantasy-league.vercel.app**

Для production-конфигурации:

1. Настрой переменные окружения Backend на Render.
2. Укажи корректный `DATABASE_URL`.
3. Установи надёжные постоянные значения `JWT_SECRET` и `ENCRYPTION_KEY`.
4. Укажи production-origin Frontend в `CORS_ORIGINS`.
5. Настрой `NEXT_PUBLIC_API_URL` во Frontend на URL Backend.
6. При использовании Telegram настрой токен, имя бота и webhook secret.
7. Проверь миграции, логи запуска, health endpoint и основные пользовательские сценарии.
8. Настрой и протестируй резервное копирование PostgreSQL.

Для запуска Backend на Render используется `backend/start.sh`. Скрипт запускает Uvicorn на порту, предоставленном окружением, с настройками proxy headers.

---

## 🧭 Направление развития

Основные направления проекта:

- дальнейшая настройка справедливости XP для спортсменов с разным тренировочным объёмом;
- развитие недельных квестов, целей и execution bonuses;
- повышение качества аналитики тренировок и восстановления;
- развитие клубов, дуэлей, лиг и рейтингов;
- улучшение мобильного интерфейса;
- укрепление приватности и надёжности синхронизации.

---

<p align="center">
  <strong>Endurance Fantasy League</strong><br>
  <em>We don't follow chaos. We set the plan.</em>
</p>
