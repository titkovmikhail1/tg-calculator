# Telegram-бот с калькулятором

Бот на Python и `aiogram 3` открывает мини-приложение Telegram для расчёта стоимости.

## Получение токена

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather).
2. Выполните `/newbot`, задайте имя и username бота.
3. Скопируйте выданный токен в `config.py` вместо `YOUR_BOT_TOKEN_HERE`.

## Настройка Web App

1. Разместите содержимое папки `webapp` на статическом HTTPS-хостинге.
2. В `config.py` укажите публичный URL страницы `index.html` вместо `https://your-domain.com/webapp`.
3. В @BotFather можно настроить кнопку меню через `/setmenubutton` и выбрать тип `Web App`, указав тот же URL. Кнопка из `/start` уже использует этот URL.

Telegram требует HTTPS-адрес для Web App (исключение — тестирование с локальным Bot API server).

## Запуск локально

Требуется Python 3.11 или новее.

```bash
cd project
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

## Развёртывание Web App

Папку `webapp` можно опубликовать через GitHub Pages, Vercel или любой статический хостинг с HTTPS. Для Vercel достаточно выбрать корневой каталог `webapp` как директорию проекта. После публикации обновите `WEBAPP_URL` в `config.py` и перезапустите бота.

## Формула

Базовый расчёт: `input_number / 0.8 * 1.4`.

Затем последовательно применяются ЕРИД (`* 1.03`), Срочно (`* 1.1`) и деление на `0.94` для Газпрома или на `0.87` в остальных случаях. Результат округляется до двух знаков математическим округлением. Бот пересчитывает данные самостоятельно и не доверяет присланному из Web App результату.
