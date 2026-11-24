# Windows — обновление и запуск SkyHop

Проект уже находится в папке пользователя: `%USERPROFILE%\interactive-surface`.
SkyHop пока находится в ветке `feature/skyhop-sticker-jump`, PR #7, не в main.

## CMD

Остановите запущенный сервер через Ctrl+C, откройте командную строку (CMD) и выполните:

```cmd
cd /d "%USERPROFILE%\interactive-surface" && git fetch origin && git switch feature/skyhop-sticker-jump && git pull --ff-only origin feature/skyhop-sticker-jump && start.bat
```

Команда обновляет существующую папку и запускает приложение. При ошибке Git следующие команды не выполняются. Если Git сообщает о локальных изменениях, проверьте git status и сохраните их; не используйте reset --hard.

## PowerShell

```powershell
Set-Location "$env:USERPROFILE\interactive-surface"
git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
git switch feature/skyhop-sticker-jump
if ($LASTEXITCODE -ne 0) { throw "git switch failed" }
git pull --ff-only origin feature/skyhop-sticker-jump
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
.\start.bat
```

start.bat создаёт виртуальное окружение и устанавливает зависимости при первом запуске. При последующих запусках используется существующая .venv. В этой ветке новых зависимостей нет. При необходимости обновить установку вручную из CMD (если .venv уже существует):

```cmd
.venv\Scripts\python.exe -m pip install -e ".[windows]"
start.bat
```

## После запуска

- Панель игр: http://127.0.0.1:8765/games
- Виртуальный проектор: http://127.0.0.1:8765/virtual-projector?showcase=1
- Выберите SkyHop в списке игр. Preview и Auto Demo доступны без физической камеры.
- Для реальной игры проверьте сохранённую калибровку и распознавание на том же оборудовании.
- Калибровка хранится вне репозитория. Обновление Git её не удаляет.

## Возврат к стабильной версии main

Остановите сервер (Ctrl+C) и выполните в CMD:

```cmd
cd /d "%USERPROFILE%\interactive-surface" && git fetch origin && git switch main && git pull --ff-only origin main && start.bat
```
