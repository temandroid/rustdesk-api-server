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
deploy/                  Деплой: скрипты для сервера (Docker и systemd), docker-compose.yml, unit-файл systemd, пример настроек
Dockerfile               Образ сервера
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
| `ID_SERVER` | Адрес ID-сервера RustDesk (hbbs). Если задан, скрипты установки отдаются уже с настройками сервера. | пусто |
| `RELAY_SERVER` | Адрес relay-сервера (hbbr), если он отличается от `ID_SERVER`. | пусто |
| `RUSTDESK_KEY` | Публичный ключ hbbs (`data/id_ed25519.pub`). | пусто |
| `API_URL` | Публичный адрес этого API для клиентов, например `https://rustdesk-api.example.com`. | адрес, по которому открыта страница |
| `RUSTDESK_CONFIG` | Готовая строка конфигурации сервера из клиента RustDesk. Если не задана, собирается из `ID_SERVER`, `RELAY_SERVER`, `RUSTDESK_KEY` и `API_URL`. | пусто |
| `RUSTDESK_VERSION` | Версия клиента RustDesk, которую скачивают скрипты установки. | `1.3.9` |
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
- **Docker image** — сборка образа, миграции и запуск контейнера с проверкой ответа;
- **Tests** — на Python 3.10, 3.12 и 3.13: `manage.py check`, проверка, что миграции не отстают от моделей, применение миграций к пустой базе, `collectstatic` и тесты;
- **Dependency vulnerabilities** — `pip-audit` по `requirements.txt`.

Изменения в любых файлах требуют ревью владельца репозитория (`.github/CODEOWNERS`).

## Деплой на сервер

После каждого push в `master` (то есть после слияния PR) и успешного прохождения всех проверок CI job **Deploy to production** выкатывает код на сервер. Push в `dev` так же выкатывается на **staging**, если он включён (см. [Staging](#staging-деплой-из-dev)). Запустить деплой вручную можно в Actions → CI → Run workflow, выбрав ветку `master` или `dev`.

| Ветка | Окружение GitHub | Метка runner'а | Каталог по умолчанию |
|-------|------------------|----------------|----------------------|
| `master` | `production` | `rustdesk-deploy` | `/opt/rustdesk-api` |
| `dev` | `staging` | `rustdesk-staging` | `/opt/rustdesk-api-staging` |

Сам деплой описан в `.github/workflows/deploy.yml`, его вызывает `ci.yml` для каждого окружения.

Как job попадает на сервер, задаёт переменная репозитория `DEPLOY_VIA` (Settings → Secrets and variables → Actions → Variables):

| `DEPLOY_VIA` | Как работает | Когда подходит |
|--------------|--------------|----------------|
| не задана (по умолчанию) | Job выполняется на **self-hosted runner**, установленном на самом сервере (метка `rustdesk-deploy`). Runner сам подключается к GitHub исходящим HTTPS-соединением, входящие порты открывать не нужно. | Сервер недоступен из интернета по SSH: закрытый порт, NAT, внутренняя сеть. |
| `ssh` | Job выполняется на обычном раннере GitHub и подключается к серверу по SSH. | На сервер можно зайти по SSH из интернета. |

Дальше для обоих вариантов одинаково:

1. Код копируется через `rsync` в новый каталог `<DEPLOY_PATH>/releases/<commit>`. Что не копируется, перечислено в `deploy/rsync-exclude.txt`.
2. На сервере запускается `deploy/remote-deploy.sh`. Он выбирает способ по `DEPLOY_METHOD` в `<DEPLOY_PATH>/shared/.env`.
3. Перед миграциями делается резервная копия базы в `<DEPLOY_PATH>/backups`. База лежит в `<DEPLOY_PATH>/shared/db/db.sqlite3`.
4. После запуска скрипт проверяет, что сервер отвечает (`HEALTHCHECK_URL`). Если сервер не ответил или упали миграции, скрипт возвращает предыдущую версию и базу из резервной копии, и job завершается ошибкой.
5. Хранятся последние 5 релизов и 10 резервных копий базы.

| `DEPLOY_METHOD` | Как запускается сервер | Что нужно на сервере |
|-----------------|------------------------|----------------------|
| `docker` (по умолчанию) | Образ собирается на сервере из `Dockerfile` и запускается через `deploy/docker-compose.yml` (контейнер `rustdesk-api`, `network_mode: host`, порт 21114) — так же, как `hbbs`/`hbbr` из официального образа RustDesk. | Docker с плагином `compose`, `rsync`, `curl` |
| `systemd` | Python-окружение `<DEPLOY_PATH>/venv`, симлинк `<DEPLOY_PATH>/current` на активный релиз, сервис systemd `deploy/rustdesk-api.service`. | Python 3.10+ с `venv`, `rsync`, `curl`, желательно `sqlite3` |

### Подготовка сервера (один раз)

Общие шаги:

```bash
# пользователь для деплоя и каталоги
sudo useradd --create-home --shell /bin/bash deploy
sudo mkdir -p /opt/rustdesk-api/shared/db
sudo chown -R deploy:deploy /opt/rustdesk-api

# настройки: скопируйте deploy/env.example в /opt/rustdesk-api/shared/.env и заполните
sudo -u deploy nano /opt/rustdesk-api/shared/.env
sudo chmod 600 /opt/rustdesk-api/shared/.env
```

В `ALLOWED_HOSTS` должен быть `127.0.0.1`: к этому адресу обращается проверка после деплоя. Ключ для `RUSTDESK_KEY` лежит в каталоге данных `hbbs` — в файле `data/id_ed25519.pub` рядом с его `docker-compose.yml`.

**Для `DEPLOY_METHOD=docker`** пользователю `deploy` нужен доступ к Docker:

```bash
sudo usermod -aG docker deploy
```

Контейнер работает от имени пользователя `deploy`, поэтому база в `shared/db` принадлежит ему. Отдельный compose-проект `rustdesk-api` не затрагивает контейнеры `hbbs` и `hbbr`. Имейте в виду, что членство в группе `docker` фактически даёт права root на сервере.

**Для `DEPLOY_METHOD=systemd`:**

```bash
sudo cp deploy/rustdesk-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rustdesk-api

# разрешить пользователю deploy только перезапуск сервиса
echo 'deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart rustdesk-api' | sudo tee /etc/sudoers.d/rustdesk-api
sudo chmod 440 /etc/sudoers.d/rustdesk-api
```

Если сервер уже работал из клона git, перенесите базу в `/opt/rustdesk-api/shared/db/db.sqlite3` до первого деплоя.

### Доступ только через Nginx Proxy Manager

По умолчанию контейнер слушает порт 21114 на всех интерфейсах сервера, как `hbbs`/`hbbr`. Чтобы веб-интерфейс и API были доступны только через reverse proxy на том же сервере, например через Nginx Proxy Manager (NPM), выберите вариант по тому, как запущен NPM. Посмотреть можно так:

```bash
docker inspect <контейнер NPM> --format '{{.HostConfig.NetworkMode}}'
```

**NPM в сети `host`** — команда выводит `host`. Сервер продолжает работать в сети хоста, но слушает только `127.0.0.1`. Добавьте в `<DEPLOY_PATH>/shared/.env`:

```bash
BIND_ADDRESS=127.0.0.1
BEHIND_PROXY=true               # NPM принимает HTTPS: ссылки в интерфейсе будут с https
ALLOWED_HOSTS=rustdesk.example.com,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://rustdesk.example.com
```

В NPM в поле **Forward Hostname / IP** укажите `127.0.0.1`.

**NPM в своей Docker-сети** — команда выводит имя сети, например `npm_default`. Контейнер подключается к этой сети, а на сервере порт открыт только на `127.0.0.1`. Добавьте в `.env`:

```bash
NETWORK_MODE=proxy
PROXY_NETWORK=npm_default       # сеть NPM из команды выше
BEHIND_PROXY=true
ALLOWED_HOSTS=rustdesk.example.com,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://rustdesk.example.com
```

В NPM в поле **Forward Hostname / IP** укажите `rustdesk-api` — это имя контейнера (для staging — `rustdesk-api-staging`).

Дальше для обоих вариантов:

1. Запустите деплой: Actions → CI → Run workflow, ветка `master`. Контейнер пересоздастся с новыми настройками.
2. В NPM создайте Proxy Host: домен `rustdesk.example.com`, Scheme `http`, Forward Hostname/IP — как указано выше, Forward Port `21114` (для staging — `21115`). На вкладке SSL выпустите сертификат и включите Force SSL.
3. В клиентах RustDesk укажите **API server** `https://rustdesk.example.com`. Если поле пустое, клиент обращается напрямую к `http://<ID server>:21114`, а этот порт снаружи будет закрыт.

### Self-hosted runner (вариант по умолчанию)

1. В GitHub откройте **Settings → Actions → Runners → New self-hosted runner**, выберите Linux и свою архитектуру. GitHub покажет команды с одноразовым токеном.
2. Выполните их на сервере от имени пользователя `deploy` в его домашнем каталоге. В команде `config.sh` добавьте метку `rustdesk-deploy`:

```bash
sudo -iu deploy
mkdir actions-runner && cd actions-runner
# скачивание и распаковка — командами со страницы GitHub
./config.sh --url https://github.com/temandroid/rustdesk-api-server --token <токен со страницы GitHub> \
  --name rustdesk-prod --labels rustdesk-deploy --unattended
exit
```

3. Установите runner как сервис, который работает от пользователя `deploy`:

```bash
cd ~deploy/actions-runner
sudo ./svc.sh install deploy
sudo ./svc.sh start
```

После этого runner появится в Settings → Actions → Runners со статусом Idle.

Про безопасность runner'а:

- На runner'е выполняется только job деплоя из `master` в окружении `production`. Все проверки и PR выполняются на раннерах GitHub.
- Runner работает с правами пользователя `deploy`. Если репозиторий станет публичным, кто угодно сможет открыть PR, поэтому не меняйте `runs-on` у других jobs на `self-hosted`.
- Серверу нужен только исходящий доступ к GitHub по HTTPS.

### Вариант через SSH (`DEPLOY_VIA=ssh`)

SSH-ключ только для деплоя:

```bash
ssh-keygen -t ed25519 -N '' -f rustdesk-deploy -C github-deploy
# открытый ключ — на сервер
sudo -u deploy mkdir -p ~deploy/.ssh
cat rustdesk-deploy.pub | sudo -u deploy tee -a ~deploy/.ssh/authorized_keys
# ключ хоста сервера для проверки подлинности (сверьте отпечаток с сервером)
ssh-keyscan -p 22 <адрес сервера>
```

Порт SSH должен быть доступен из интернета: раннеры GitHub подключаются с меняющихся адресов.

### Настройка GitHub (один раз)

В **Settings → Environments** создайте окружение `production`:

- **Deployment branches and tags:** только `master`.
- **Required reviewers:** добавьте себя. Тогда каждый деплой ждёт вашего подтверждения в Actions. Если не нужно, пропустите.
- **Environment secrets:**

| Секрет | Значение | Нужен для |
|--------|----------|-----------|
| `DEPLOY_PATH` | каталог приложения на сервере | обоих вариантов (необязательно, по умолчанию `/opt/rustdesk-api`) |
| `SSH_HOST` | адрес сервера | `DEPLOY_VIA=ssh` |
| `SSH_USER` | `deploy` | `DEPLOY_VIA=ssh` |
| `SSH_PORT` | порт SSH (необязательно, по умолчанию 22) | `DEPLOY_VIA=ssh` |
| `SSH_PRIVATE_KEY` | содержимое файла `rustdesk-deploy` (закрытый ключ) | `DEPLOY_VIA=ssh` |
| `SSH_KNOWN_HOSTS` | вывод `ssh-keyscan` | `DEPLOY_VIA=ssh` |

### Диагностика

Workflow **Diagnostics** (Actions → Diagnostics → Run workflow) запускается вручную на том же self-hosted runner'е и ничего не меняет. Он показывает текущий релиз и последние бэкапы, переменные из `shared/.env` (значения секретных, например `SECRET_KEY`, скрыты), состояние контейнера и его сети, хвост лога, сводку кодов ответа и HTTP-проверки: напрямую, из контейнера reverse proxy (`proxy-container`) и снаружи (`public-url`). Лог попадает в журнал Actions — в нём есть IP-адреса и ID клиентов.

### Ручной откат

Docker:

```bash
cd /opt/rustdesk-api
ls releases                       # доступные релизы
APP_DIR=/opt/rustdesk-api INSTANCE_NAME=rustdesk-api APP_UID=$(id -u) APP_GID=$(id -g) IMAGE_TAG=<commit> \
  docker compose -f releases/<commit>/deploy/docker-compose.yml up -d
echo <commit> > current_release
```

systemd:

```bash
ln -sfn /opt/rustdesk-api/releases/<commit> /opt/rustdesk-api/current
sudo systemctl restart rustdesk-api
```

Резервные копии базы — в `/opt/rustdesk-api/backups`.

Для staging то же самое, но с каталогом `/opt/rustdesk-api-staging` и `INSTANCE_NAME=rustdesk-api-staging`.

### Staging: деплой из `dev`

Staging — отдельный экземпляр сервера для проверки изменений до слияния в `master`. У него своя база, свой порт и свои настройки. Настоящие клиенты RustDesk к нему не подключаются.

Staging можно поднять на том же сервере, что и прод, или на отдельном. Для одного сервера:

1. Создайте каталог и настройки:

```bash
sudo mkdir -p /opt/rustdesk-api-staging/shared/db
sudo chown -R deploy:deploy /opt/rustdesk-api-staging
# скопируйте deploy/env.example в /opt/rustdesk-api-staging/shared/.env и заполните
sudo -u deploy nano /opt/rustdesk-api-staging/shared/.env
sudo chmod 600 /opt/rustdesk-api-staging/shared/.env
```

В `.env` для staging обязательно:

```bash
SECRET_KEY=<другой, не как на проде>
INSTANCE_NAME=rustdesk-api-staging   # имя контейнера, образа и compose-проекта
APP_PORT=21115                       # порт, отличный от прода (21114)
ALLOWED_HOSTS=<адрес сервера>,127.0.0.1
```

Для `DEPLOY_METHOD=systemd` вместо `INSTANCE_NAME` нужен отдельный сервис: скопируйте `deploy/rustdesk-api.service` в `rustdesk-api-staging.service`, поменяйте в нём пути на `/opt/rustdesk-api-staging` и порт на 21115, а в `.env` укажите `SERVICE_NAME=rustdesk-api-staging` и `APP_PORT=21115`. Правило sudoers тоже нужно добавить для нового сервиса.

2. Добавьте runner'у метку `rustdesk-staging` в Settings → Actions → Runners. Один runner может обслуживать оба окружения: деплои выполняются по очереди. Если staging на отдельном сервере, установите туда свой runner с этой меткой.

3. В **Settings → Environments** создайте окружение `staging`. В **Deployment branches and tags** разрешите только `dev`. Если каталог не `/opt/rustdesk-api-staging`, добавьте секрет `DEPLOY_PATH`.

4. Включите staging: в **Settings → Secrets and variables → Actions → Variables** создайте переменную репозитория `STAGING_ENABLED` со значением `true`. Пока её нет, job **Deploy to staging** пропускается. Это нужно, чтобы push в `dev` не ждал runner'а, которого ещё нет.

После этого каждый push в `dev` после зелёных проверок выкатывается на `http://<сервер>:21115/`. Администратора на staging создайте отдельно: `docker exec -it rustdesk-api-staging python manage.py createsuperuser`.

## Настройка клиента RustDesk

В клиенте откройте **Настройки → Сеть → ID/Relay сервер** и укажите:

- **ID server** — адрес вашего hbbs;
- **Relay server** — адрес вашего hbbr;
- **API server** — `http://<сервер>:21114` (или HTTPS-адрес за reverse proxy);
- **Key** — публичный ключ hbbs.

После этого войдите в клиенте под пользователем, созданным на сервере. Адресная книга будет синхронизироваться с сервером, а устройство появится в веб-интерфейсе.

## Скрипты установки клиента

В `static/configs/` лежат скрипты для массовой установки клиента: `install.bat`, `install.ps1` (Windows), `install-linux.sh`, `install-mac.sh`. Скрипт ставит RustDesk нужной версии, задаёт случайный пароль и применяет настройки сервера (`rustdesk --config`).

Скачивать их нужно со страницы `/api/installers` (или по ссылкам `/api/installers/<имя скрипта>`): сервер подставляет в них версию из `RUSTDESK_VERSION` и строку конфигурации — ID-сервер, relay, адрес API и ключ. Для этого в настройках достаточно задать `ID_SERVER` и `RUSTDESK_KEY`; строка собирается автоматически в том же формате, что экспортирует клиент (**Настройки → Сеть → Экспорт конфигурации сервера**). Ссылки на скрипты открываются без входа, чтобы их можно было скачать прямо на устанавливаемой машине:

```bash
curl -fsSL https://rustdesk-api.example.com/api/installers/install-linux.sh | sudo bash
```

В скрипты попадают только адреса серверов и публичный ключ — то же, что и так получает каждый клиент.

На странице также показаны адрес API, ключ и строка конфигурации: её можно вставить в уже установленный клиент (**Настройки → Сеть → Импорт конфигурации сервера**). Ссылка на `rustdesk-licensed-<строка конфигурации>.exe` и QR-код `qrcode.png` появляются, если положить эти файлы в `static/configs/`.

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
