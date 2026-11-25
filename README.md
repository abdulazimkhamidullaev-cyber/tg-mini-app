# Telegram Mini App starter (tasks)

A bot plus a Mini App that runs inside Telegram, served together by `app.py`.

```
app.py            bot (aiogram 3) + web server (aiohttp) + SQLite API
webapp/           the Mini App: index.html, style.css, app.js
```

## Run it

1. Create a bot with @BotFather (`/newbot`) and copy the token.
2. Install the dependencies: `pip install -r requirements.txt`
3. Telegram only opens HTTPS URLs. For local testing, tunnel port 8080: `ngrok http 8080`
4. `cp .env.example .env`, then fill in BOT_TOKEN and WEBAPP_URL (the ngrok https URL).
5. `python app.py`, then send /start to your bot and tap **Open my tasks**.

## How auth works
Telegram passes the app a signed `initData` string. The frontend sends it as
`Authorization: tma <initData>` and the server checks the HMAC against the bot token,
so a user can't pretend to be someone else.
