# Карта информационной архитектуры — этап 0

Линии относятся к исходному состоянию `main` до PR. Таблица — инвентаризация, а не удаление или немедленный перенос маршрутов. В этапе 0 текущее поведение сохраняется.

| Контейнер | Было (файл: строки в main) | Станет (целевая страница / место) |
|---|---|---|
| Dashboard: guest / empty state | `frontend/src/app/dashboard/page.tsx:557–595` | `/dashboard` — empty state |
| Dashboard: Progress header / athlete identity | `frontend/src/app/dashboard/page.tsx:596–613` | `/dashboard` — status header |
| Dashboard: Level / streak / weekly goal | `frontend/src/app/dashboard/page.tsx:616–660` | `/dashboard` — compact progress summary |
| WeekBlock: week picker, load goal, XP split, pause | `frontend/src/app/dashboard/page.tsx:57–189` | `/dashboard` — weekly goal |
| EventsFeed: weekly XP events | `frontend/src/app/dashboard/page.tsx:190–215` | `/dashboard` — XP events |
| SeasonWeeksChart | `frontend/src/app/dashboard/page.tsx:216–248` | `/training` — season by weeks |
| QuestsBoard / achievements | `frontend/src/app/dashboard/page.tsx:249–285` | `/dashboard` — short achievements |
| Rating board: global / friends / weekly | `frontend/src/app/dashboard/page.tsx:694–854` | `/compete` → Rating |
| XP Dynamics chart | `frontend/src/app/dashboard/page.tsx:855–922` | `/training` — XP Dynamics |
| Workouts list / ActivityCard | `frontend/src/app/dashboard/page.tsx:923–956` | `/training` — workouts by week |
| Dashboard: pause dialog and API errors | `frontend/src/app/dashboard/page.tsx:511–539` | `/dashboard` — preserve pause/error behavior |
| Profile: header / messages | `frontend/src/app/profile/page.tsx:116–147` | `/profile` — identity/messages |
| Profile: athlete business card / name / level / XP / friends | `frontend/src/app/profile/page.tsx:148–182` | `/profile` — business card |
| Profile: season statistics | `frontend/src/app/profile/page.tsx:183–207` | `/profile` — seasonal totals |
| SocialHub: PersonRow / friend search and list modals | `frontend/src/components/SocialHub.tsx:24–422` | `/profile` — friends |
| SocialHub: club discovery, requests, details, owner actions | `frontend/src/components/SocialHub.tsx:423–998` | `/compete` → Clubs |
| SocialHub: outer tabs and modal orchestration | `frontend/src/components/SocialHub.tsx:999–1072` | `/profile` Friends / `/compete` Clubs |
| ConnectSources: integration credentials, sync controls and source status | `frontend/src/components/ConnectSources.tsx:1–401` | Settings → Sources; `/training` → operational sync/status; proposed split to confirm |
| TelegramBind: link code, notify, unlink | `frontend/src/components/TelegramBind.tsx:1–149` | Settings → Sources → Telegram |
| ActivityUpload: file selection, preview, validation, confirm | `frontend/src/components/ActivityUpload.tsx:1–249` | `/training` → upload file |
| HeartRateSettings: LTHR / max HR / resting HR / timezone | `frontend/src/components/HeartRateSettings.tsx:1–139` | Settings → Training and heart rate |
| AccountPrivacy: consent and profile/activity visibility | `frontend/src/components/AccountPrivacy.tsx:95–165` | Settings → Privacy |
| AccountPrivacy: TelegramBind mount | `frontend/src/components/AccountPrivacy.tsx:166` | Extract to Settings → Sources → Telegram |
| AccountPrivacy: delete-account / confirmation | `frontend/src/components/AccountPrivacy.tsx:168–186` | Settings → Dangerous zone |
| Profile: clear training data / logout / reset confirmation | `frontend/src/app/profile/page.tsx:266–293` | Settings → Account / Dangerous zone |
| Duels: page heading / competition summary | `frontend/src/app/duels/page.tsx:111–116` | `/compete` → Duels |
| Duels: challenge form, friend picker, feedback | `frontend/src/app/duels/page.tsx:118–135` | `/compete` → Duels |
| Duels: duel list, statuses, accept/decline | `frontend/src/app/duels/page.tsx:136–183` | `/compete` → Duels |

## Вопросы размещения

1. `ConnectSources` совмещает настройку интеграции и операционный синк/статус. Предлагаемое разделение: ключи и привязки — Настройки → Источники данных; синхронизация и оперативное состояние — `/training`. UI/API не дублируются в этом PR.
2. `ActivityUpload` целится на `/training`, потому что загрузка файла включена в требования этой страницы. Настройки → «Тренировки и пульс» содержит параметры зон ЧСС (`HeartRateSettings`).
3. `SocialHub` объединяет друзей и клубы. Целевое разделение: друзья остаются в профиле, клубы идут в `/compete` → Clubs. Перемещение клубного UI — отдельный этап.
4. Существующий маршрут `/duels` не переименовывается здесь; целевое место — `/compete` → Duels в этапе маршрутизации.
