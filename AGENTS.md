# AGENTS.md - EkanjiBot Knowledge Base

**Generated:** 2026-04-02
**Commit:** 2762032
**Branch:** master

## OVERVIEW

Telegram bot converting text to custom emoji stickers using aiogram 3.x + SQLModel + async SQLite. Supports multi-font rendering, inline mode, and intelligent character caching.

## STRUCTURE

```
EkanjiBot/
├── bot.py              # Entry point, startup hooks
├── log.py              # Loguru config (root-level, non-standard)
├── alembic.ini         # Alembic configuration
├── migrations/         # Database migrations (Alembic)
│   ├── env.py          # Migration environment config
│   └── versions/       # Migration scripts
├── core/               # Config (bs singleton), database engine
├── db/                 # Models + repositories (Repository pattern)
│   ├── models/         # SQLModel tables: User, Font, CharacterGlyph, StickerSet
│   └── repositories/   # CRUD + domain queries (see db/AGENTS.md)
├── handlers/           # aiogram routers (see handlers/AGENTS.md)
│   ├── commands/       # /start, /fonts, /sf, /rf
│   ├── messages/       # Text → emoji conversion
│   └── inline/         # Inline query handler
├── middlewares/        # DatabaseMiddleware, UserContextMiddleware
├── services/           # StickerService, FontSyncService, ImageRenderer (see services/AGENTS.md)
├── utils/              # Event loop optimization (winloop/uvloop)
├── assets/fonts/       # Font files (.ttf, .otf) - GITIGNORED
├── data/               # SQLite database, runtime data - GITIGNORED
└── logs/               # Log files - GITIGNORED
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add new command | `handlers/commands/` | Register in `handlers/__init__.py` |
| Change font logic | `services/font_sync_service.py` | FontSyncService syncs assets/fonts/ → DB |
| Add DB model | `db/models/` | Export in `db/models/__init__.py` + create migration |
| Add DB query | `db/repositories/` | Extend BaseRepository |
| Fix sticker creation | `services/sticker_service.py` | StickerService handles locking, caching |
| Change config | `core/config.py` | BotSettings singleton `bs` |
| Fix DB locks | `core/database.py` | NullPool + WAL mode + busy_timeout |
| Add middleware | `middlewares/` | Register in `handlers/__init__.py:setup_handlers()` |
| Database migration | `migrations/` | Use `alembic revision --autogenerate` |

## CONVENTIONS

- **Python 3.12+**: `X | None` not `Optional[X]`, `list[X]` not `List[X]`
- **Line length**: 120 chars
- **Imports**: stdlib → third-party → local (blank lines between)
- **Docstrings**: Google style, mandatory for public APIs
- **Type hints**: Required on all public functions/class attributes
- **Naming**: `PascalCase` classes, `snake_case` functions/vars, `UPPER_CASE` constants
- **Private methods**: `_leading_underscore`
- **Type variables**: `ModelType` not `T`

## ANTI-PATTERNS (THIS PROJECT)

- **NEVER** commit `assets/fonts/*` — copyright issues
- **NEVER** commit `.env` — contains BOT_TOKEN
- **NEVER** use bare `except:` — use `except Exception:` or specific
- **NEVER** use `as any`, `@ts-ignore` (N/A for Python, but mindset applies)
- **ALWAYS** use `logger.exception()` in except blocks for full traceback

## UNIQUE STYLES

### SQLite Concurrency Pattern
```python
# core/database.py - CRITICAL for avoiding locks
async_engine = create_async_engine(
    url,
    poolclass=NullPool,        # No connection reuse
    connect_args={"timeout": 60.0}
)
# PRAGMA: journal_mode=WAL, busy_timeout=60000ms
```

### Sticker Creation Task Queue
```python
# services/sticker_service.py - Global serial queue
# Only ONE sticker creation at a time globally
# Prevents race conditions, simplifies caching
class StickerTaskQueue:
    _queue: asyncio.Queue[StickerCreationTask]
    _worker_task: asyncio.Task  # Background worker

    async def submit(task) -> str:  # Wait for result
    async def _worker():  # Process tasks serially
```

### Task-Based Creation
```python
# Handlers submit tasks, queue processes serially
task = StickerCreationTask(
    user_id, character, font_id, font_path, image_bytes, bot_username
)
emoji_id = await queue.submit(task)  # Blocks until done
```

## COMMANDS

```bash
# Development
uv sync                    # Install dependencies
uv run bot.py              # Run bot locally
uv run ruff check .        # Lint
uv run ruff check . --fix  # Auto-fix
uv run ruff format .       # Format

# Database Migrations
uv run alembic revision --autogenerate -m "description"  # Create migration
uv run alembic upgrade head                              # Apply migrations
uv run alembic downgrade -1                              # Rollback 1 version
uv run alembic current                                   # Show current version
uv run alembic history                                   # Show migration history

# Production
sudo sh start.sh           # Docker build + start
```

## NOTES

- **No test suite** — planned for `tests/` with pytest
- **Text limit**: 120 chars max per request
- **Default font**: First with letters/Chinese at start of name (sorted: letters > numbers)
- **Sticker pack size**: 120 stickers per pack (Telegram limit)
- **DB migrations**: Use `alembic upgrade head` to apply, not `init_db()` in bot.py
- **DB reset**: Delete `data/` folder + re-run `alembic upgrade head` (orphaned stickers in Telegram)
- **UI language**: Chinese (中文) for all bot messages
