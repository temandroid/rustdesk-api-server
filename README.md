# rustdesk-api-server

Самостоятельно размещаемый API-сервер для клиента [RustDesk](https://rustdesk.com), написанный на Python/Django, с веб-интерфейсом для управления устройствами.

Сервер реализует HTTP API, которое клиент RustDesk использует для входа в аккаунт, синхронизации адресной книги, отправки информации об устройстве и журналов аудита. Он заменяет платный сервер API RustDesk Pro для небольших установок.

> Проект — форк [kingmo888/rustdesk-api-server](https://github.com/kingmo888/rustdesk-api-server)
> с англоязычным интерфейсом, журналами подключений и передачи файлов, а также скриптами установки клиента.

> ⚠️ **Безопасность.** Проблемы из [CODE_REVIEW.md](CODE_REVIEW.md) исправлены, но
> эндпоинты `/api/sysinfo`, `/api/heartbeat` и `/api/audit` по протоколу RustDesk вызываются
> клиентом без токена и остаются без аутентификации. Выставляйте сервер в интернет только
> за reverse proxy с HTTPS.

## Возможности

- **API для клиента RustDesk**: вход/выход, текущий пользователь, адресная книга (`/api/ab`) с тегами и цветами тегов, отправка системной информации (`/api/sysinfo`), heartbeat, аудит подключений и передачи файлов.
- **Веб-интерфейс** (`/api/work`):
  - список своих устройств с версией клиента, ОС, CPU, памятью, IP и статусом;
  - для администраторов — список всех устройств, зарегистрированных на сервере, и назначение устройства пользователю;
  - добавление, редактирование и удаление устройств в адресной книге;
  - передача устройств другому пользователю через одноразовую ссылку, действующую 15 минут (`/api/share`);
  - для администраторов — журнал подключений (`/api/conn_log`) и журнал передачи файлов (`/api/file_log`);
  - страница со скриптами установки клиента (`/api/installers`).
- **Админ-панель Django** (`/admin`): пользователи, токены, теги, устройства, ссылки, журналы.

## Требования

- Python 3.10+
- Django 4.2–5.x (проверено на 5.2) и gunicorn — см. `requirements.txt`
- SQLite (файл `db/db.sqlite3` создаётся командой `migrate`)

## Структура проекта

```
rustdesk_server_api/     Настройки Django-проекта (settings.py, urls.py, wsgi/asgi)
deploy/                  Деплой: скрипт для сервера, unit-файл systemd, пример настроек
api/
  models_user.py         Модель пользователя UserProfile и менеджер
  models_work.py         Токены, теги, устройства (peers/devices), журналы, ссылки общего доступа
  views_api.py           Эндпоинты, которые вызывает клиент RustDesk
  views_front.py         Страницы веб-интерфейса
  admin.py               Регистрация моделей в админ-панели
  forms.py               Формы добавления/редактирования/назначения устройств
  templates/             HTML-шаблоны (layui)
  tests.py               Тесты
  management/commands/   Команда securecreatesuperuser (синоним createsuperuser)
db/                      Каталог базы данных SQLite (сама база не хранится в git)
static/                  Статика: layui и скрипты установки клиента (static/configs)
```

## Установка и запуск

### 1. Клонирование и зависимости

```bash
git clone https://github.com/temandroid/rustdesk-api-server.git
cd rustdesk-api-server
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройки

Настройки задаются переменными окружения. Их также можно записать в файл `rustdesk_server_api/secret_config.py` (он в `.gitignore`); переменные окружения важнее файла.

| Переменная  | Назначение | По умолчанию |
|-------------|------------|--------------|
| `SECRET_KEY` | **Обязательно.** Секретный ключ Django. Без него сервер не запустится. | — |
| `CSRF_TRUSTED_ORIGINS` | Адреса, по которым открывается веб-интерфейс, через запятую, со схемой: `https://rustdesk-api.example.com`. Нужны для входа через HTTPS reverse proxy. | пусто |
| `ALLOWED_HOSTS` | Имена хостов сервера через запятую (например, `rustdesk-api.example.com`). | `*` |
| `DEBUG` | Режим отладки Django: `1`, `true`, `yes` или `on` включают его, любое другое значение — выключает. Не включайте в продакшене. | выключен |
| `ID_SERVER` | Адрес ID-сервера RustDesk (hbbs). | пусто |
| `RUSTDESK_KEY` | Публичный ключ hbbs — показывается на странице установщиков. | пусто |
| `RUSTDESK_CONFIG` | Строка конфигурации сервера из клиента RustDesk — показывается на странице установщиков. | пусто |
| `TIME_ZONE` | Часовой пояс, в котором хранятся и показываются даты, например `Europe/Moscow`. | `UTC` |
| `DB_PATH` | Путь к файлу базы SQLite. | `db/db.sqlite3` |
| `LOG_LEVEL` | Уровень логирования приложения. | `INFO` |

Пример `secret_config.py`:

```python
SECRET_KEY = "длинная-случайная-строка"
CSRF_TRUSTED_ORIGINS = ["https://rustdesk-api.example.com"]
```

Секретный ключ можно сгенерировать так:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 3. База данных и администратор

```bash
python manage.py migrate
python manage.py createsuperuser
```

Самостоятельной регистрации через веб-интерфейс нет — пользователей создаёт администратор в `/admin`.

### 4. Запуск

Для проверки:

```bash
python manage.py runserver 0.0.0.0:21114
```

Для постоянной работы:

```bash
gunicorn rustdesk_server_api.wsgi:application --bind 0.0.0.0:21114
```

Статика (`/static/...`) раздаётся самим приложением. Если статику отдаёт веб-сервер, выполните `python manage.py collectstatic` и направьте `/static/` на каталог `static_root/`.

Порт `21114` — стандартный порт API в RustDesk. В продакшене ставьте перед сервером reverse proxy (nginx, Caddy) с HTTPS и передавайте заголовок `X-Forwarded-For` — по нему определяется IP клиента.

Веб-интерфейс: `http://<сервер>:21114/`, админ-панель: `http://<сервер>:21114/admin`.

### Обновление с предыдущих версий

Раньше файл базы `db/db.sqlite3` хранился в git, теперь его в репозитории нет. Чтобы `git pull` не удалил рабочую базу, перед обновлением сохраните её копию:

```bash
cp db/db.sqlite3 ~/db.sqlite3.backup
git checkout -- db/db.sqlite3
git pull
cp ~/db.sqlite3.backup db/db.sqlite3
python manage.py migrate
```

Миграция `0004` переименовывает таблицу устройств и увеличивает длину полей; данные сохраняются. Если раньше вы использовали `SALT_CRED`, эта настройка больше не нужна.

### Тесты

```bash
SECRET_KEY=test python manage.py test api
```

### Проверки перед слиянием (CI)

GitHub Actions (`.github/workflows/ci.yml`) запускается на каждый PR и push в `master` и `dev`:

- **Lint** — `ruff` (синтаксические ошибки, неопределённые имена, неиспользуемые импорты) и `shellcheck` для скриптов установки;
- **Tests** — на Python 3.10, 3.12 и 3.13: `manage.py check`, проверка, что миграции не отстают от моделей, применение миграций к пустой базе, `collectstatic` и тесты;
- **Dependency vulnerabilities** — `pip-audit` по `requirements.txt`.

Изменения в любых файлах требуют ревью владельца репозитория (`.github/CODEOWNERS`).

## Деплой на сервер по SSH

После каждого push в `master` (то есть после слияния PR) и успешного прохождения всех проверок CI job **Deploy to production** выкатывает код на сервер. Запустить деплой вручную можно в Actions → CI → Run workflow (ветка `master`).

Как это работает:

1. Код копируется через `rsync` по SSH в новый каталог `<DEPLOY_PATH>/releases/<commit>`. Серверу не нужен доступ к GitHub.
2. На сервере запускается `deploy/remote-deploy.sh`:
   - ставит зависимости в `<DEPLOY_PATH>/venv`;
   - делает `manage.py check`;
   - делает резервную копию базы в `<DEPLOY_PATH>/backups`;
   - применяет миграции и `collectstatic`;
   - переключает симлинк `<DEPLOY_PATH>/current` на новый релиз и перезапускает сервис.
3. Скрипт проверяет, что сервер отвечает (`HEALTHCHECK_URL`). Если нет, он возвращает предыдущий релиз и базу из резервной копии, перезапускает сервис, и job завершается ошибкой.
4. Хранятся последние 5 релизов и 10 резервных копий базы.

### Подготовка сервера (один раз)

Нужны `python3` (3.10+) с модулем `venv`, `rsync`, `curl` и, желательно, `sqlite3` (для согласованной резервной копии базы).

```bash
# пользователь для деплоя и каталоги
sudo useradd --system --create-home --shell /bin/bash deploy
sudo mkdir -p /opt/rustdesk-api/shared/db
sudo chown -R deploy:deploy /opt/rustdesk-api

# настройки: скопируйте deploy/env.example в /opt/rustdesk-api/shared/.env и заполните
sudo -u deploy nano /opt/rustdesk-api/shared/.env
sudo chmod 600 /opt/rustdesk-api/shared/.env

# сервис
sudo cp deploy/rustdesk-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rustdesk-api

# разрешить пользователю deploy только перезапуск сервиса
echo 'deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart rustdesk-api' | sudo tee /etc/sudoers.d/rustdesk-api
sudo chmod 440 /etc/sudoers.d/rustdesk-api
```

В `ALLOWED_HOSTS` должен быть `127.0.0.1`: к этому адресу обращается проверка после деплоя. Если сервер уже работал из клона git, перенесите базу в `DB_PATH` (по умолчанию `/opt/rustdesk-api/shared/db/db.sqlite3`) до первого деплоя.

SSH-ключ только для деплоя:

```bash
ssh-keygen -t ed25519 -N '' -f rustdesk-deploy -C github-deploy
# открытый ключ — на сервер
sudo -u deploy mkdir -p ~deploy/.ssh
cat rustdesk-deploy.pub | sudo -u deploy tee -a ~deploy/.ssh/authorized_keys
# ключ хоста сервера для проверки подлинности (сверьте отпечаток с сервером)
ssh-keyscan -p 22 <адрес сервера>
```

### Настройка GitHub (один раз)

В **Settings → Environments** создайте окружение `production`:

- **Deployment branches and tags:** только `master`.
- **Required reviewers:** добавьте себя. Тогда каждый деплой ждёт вашего подтверждения в Actions. Если не нужно, пропустите.
- **Environment secrets:**

| Секрет | Значение |
|--------|----------|
| `SSH_HOST` | адрес сервера |
| `SSH_USER` | `deploy` |
| `SSH_PORT` | порт SSH (необязательно, по умолчанию 22) |
| `SSH_PRIVATE_KEY` | содержимое файла `rustdesk-deploy` (закрытый ключ) |
| `SSH_KNOWN_HOSTS` | вывод `ssh-keyscan` |
| `DEPLOY_PATH` | `/opt/rustdesk-api` |

Если нужно откатиться вручную, переключите симлинк на предыдущий релиз и перезапустите сервис:

```bash
ln -sfn /opt/rustdesk-api/releases/<commit> /opt/rustdesk-api/current
sudo systemctl restart rustdesk-api
```

## Настройка клиента RustDesk

В клиенте откройте **Настройки → Сеть → ID/Relay сервер** и укажите:

- **ID server** — адрес вашего hbbs;
- **Relay server** — адрес вашего hbbr;
- **API server** — `http://<сервер>:21114` (или HTTPS-адрес за reverse proxy);
- **Key** — публичный ключ hbbs.

После этого войдите в клиенте под пользователем, созданным на сервере. Адресная книга будет синхронизироваться с сервером, а устройство появится в веб-интерфейсе.

## Скрипты установки клиента

В `static/configs/` лежат скрипты для массовой установки клиента: `install.bat`, `install.ps1` (Windows), `install-linux.sh`, `install-mac.sh`. Перед использованием отредактируйте их:

- `VERSION` / `$version` — версия RustDesk;
- `rustdesk_cfg` — строка конфигурации сервера (экспортируется в клиенте: **Настройки → Сеть → Экспорт конфигурации сервера**) вместо заглушки `secure-string`.

Страница `/api/installers` показывает ссылки на эти скрипты, адрес API (берётся из адреса запроса), ключ (`RUSTDESK_KEY`) и строку конфигурации (`RUSTDESK_CONFIG`). Ссылка на `rustdesk-licensed-<RUSTDESK_CONFIG>.exe` и QR-код `qrcode.png` появляются, если положить эти файлы в `static/configs/`.

## API

Эндпоинты, которые вызывает клиент RustDesk (тело запросов — JSON):

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/login` | Вход. Возвращает `access_token`. |
| POST | `/api/logout` | Выход (удаляет токен устройства). |
| POST | `/api/currentUser` | Текущий пользователь по токену `Authorization: Bearer <token>`. |
| GET / POST | `/api/ab` | Получение / сохранение адресной книги (теги, цвета, устройства). |
| POST | `/api/sysinfo` | Информация об устройстве (CPU, память, ОС, версия). |
| POST | `/api/heartbeat` | Отметка «онлайн» и продление токена. |
| POST | `/api/audit/conn`, `/api/audit/file` (и `/api/audit`) | Журнал подключений и передачи файлов. |
| * | `/api/users`, `/api/peers` | Заглушки. |

Токен действует 2 часа после входа или последнего heartbeat-запроса (`EFFECTIVE_SECONDS` в `api/views_front.py`). При неверном JSON эндпоинты отвечают кодом 400 и полем `error`.

## Лицензия

GNU AGPL v3 — см. [LICENSE.rst](LICENSE.rst).
