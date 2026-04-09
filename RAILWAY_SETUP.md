# Настройка на Railway

## Шаг 1: Создай новый токен Discord
1. Зайди на https://discord.com/developers/applications
2. Выбери своего бота
3. Bot → Reset Token
4. Скопируй новый токен

## Шаг 2: Добавь переменную окружения на Railway
1. Открой свой проект на Railway
2. Перейди во вкладку **Variables**
3. Нажми **New Variable**
4. Введи:
   - **Variable Name:** `DISCORD_TOKEN`
   - **Value:** твой новый токен Discord
5. Нажми **Add**

## Шаг 3: Redeploy
Railway автоматически перезапустит бота с новым токеном.

## Для локальной разработки
Создай файл `.env` в корне проекта:
```
DISCORD_TOKEN=твой-токен
```

Этот файл не будет загружен на GitHub (он в .gitignore).
