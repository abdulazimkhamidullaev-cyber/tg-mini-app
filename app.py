"""Telegram bot + Mini App server in one process.

- The bot (aiogram 3, long polling) answers /start with a button that opens the Mini App.
- The aiohttp server serves the Mini App (webapp/) and a small JSON API.
- Every API call is authenticated by verifying Telegram's initData signature.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
from dotenv import load_dotenv

import customer

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]
# Render sets RENDER_EXTERNAL_URL automatically, so WEBAPP_URL is optional there.
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBAPP_URL = os.getenv("WEBAPP_URL") or PUBLIC_URL  # public HTTPS URL of this server
PORT = int(os.getenv("PORT", "8080"))
# On a host that sleeps when idle (Render free), use a webhook so Telegram wakes us up.
USE_WEBHOOK = bool(PUBLIC_URL) or os.getenv("USE_WEBHOOK") == "1"
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()[:32]
WEBHOOK_PATH = "/telegram-webhook"
DB_PATH = os.getenv("DB_PATH", "data.db")
INIT_DATA_MAX_AGE = 24 * 3600  # reject initData older than a day

BASE_DIR = Path(__file__).parent
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------- database
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute(
    """CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
    )"""
)
db.commit()


def task_dict(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "text": row["text"], "done": bool(row["done"])}


# ---------------------------------------------------------------- auth
def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Check the initData signature as described in Telegram's docs.

    Returns the parsed user dict, or None if the data is forged or stale.
    """
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    if time.time() - int(pairs.get("auth_date", 0)) > INIT_DATA_MAX_AGE:
        return None
    return json.loads(pairs.get("user", "null"))


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.path.startswith("/api/"):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("tma "):
            raise web.HTTPUnauthorized(text="missing initData")
        user = validate_init_data(auth[4:], BOT_TOKEN)
        if not user:
            raise web.HTTPUnauthorized(text="invalid initData")
        request["user"] = user
    return await handler(request)


# ---------------------------------------------------------------- API
routes = web.RouteTableDef()


@routes.get("/api/me")
async def me(request: web.Request):
    return web.json_response(request["user"])


@routes.get("/api/tasks")
async def list_tasks(request: web.Request):
    rows = db.execute(
        "SELECT * FROM tasks WHERE user_id=? ORDER BY done, id DESC",
        (request["user"]["id"],),
    ).fetchall()
    return web.json_response([task_dict(r) for r in rows])


@routes.post("/api/tasks")
async def add_task(request: web.Request):
    body = await request.json()
    text = str(body.get("text", "")).strip()[:200]
    if not text:
        raise web.HTTPBadRequest(text="text is required")
    cur = db.execute(
        "INSERT INTO tasks (user_id, text, created_at) VALUES (?, ?, ?)",
        (request["user"]["id"], text, int(time.time())),
    )
    db.commit()
    row = db.execute("SELECT * FROM tasks WHERE id=?", (cur.lastrowid,)).fetchone()
    return web.json_response(task_dict(row), status=201)


@routes.patch("/api/tasks/{id:\\d+}")
async def toggle_task(request: web.Request):
    body = await request.json()
    db.execute(
        "UPDATE tasks SET done=? WHERE id=? AND user_id=?",
        (int(bool(body.get("done"))), int(request.match_info["id"]), request["user"]["id"]),
    )
    db.commit()
    return web.json_response({"ok": True})


@routes.delete("/api/tasks/{id:\\d+}")
async def delete_task(request: web.Request):
    db.execute(
        "DELETE FROM tasks WHERE id=? AND user_id=?",
        (int(request.match_info["id"]), request["user"]["id"]),
    )
    db.commit()
    return web.json_response({"ok": True})


@routes.get("/health")
async def health(_: web.Request):
    return web.Response(text="ok")


@routes.get("/")
async def index(_: web.Request):
    return web.FileResponse(BASE_DIR / "webapp" / "index.html")


routes.static("/static", BASE_DIR / "webapp")


# ---------------------------------------------------------------- bot
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
# Telegram username of the shop admin that /help sends customers to.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
dp.include_router(customer.setup(db, WEBAPP_URL, ADMIN_USERNAME))


# ---------------------------------------------------------------- run
async def main():
    app = web.Application(middlewares=[auth_middleware])
    app.add_routes(routes)

    if USE_WEBHOOK:
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET).register(app, path=WEBHOOK_PATH)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info("Web server on :%s, Mini App URL %s", PORT, WEBAPP_URL)

    # Also put an "Open" button next to the chat input.
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Open app", web_app=WebAppInfo(url=WEBAPP_URL))
    )
    # Command menu ("/" button): English by default, Russian/Uzbek for those app languages.
    await bot.set_my_commands(customer.bot_commands("en"))
    for code in ("ru", "uz"):
        await bot.set_my_commands(customer.bot_commands(code), language_code=code)

    try:
        if USE_WEBHOOK:
            await bot.set_webhook(WEBAPP_URL.rstrip("/") + WEBHOOK_PATH, secret_token=WEBHOOK_SECRET)
            logging.info("Webhook mode")
            await asyncio.Event().wait()  # run forever
        else:
            await bot.delete_webhook()
            await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
