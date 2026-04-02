# AGENTS.md - handlers/

**Generated:** 2026-04-02
**Commit:** 2762032
**Branch:** master

## OVERVIEW

aiogram 3.x routers with middleware-injected session, db_user, bot dependencies.

## STRUCTURE

```
handlers/
├── __init__.py          # setup_handlers() registers middlewares + routers
├── commands/
│   ├── start.py         # /start, /lang
│   ├── font.py          # /fonts, /sf
│   └── random_font.py   # /rf (random font per character)
├── messages/
│   └── text_handler.py  # F.text filter → emoji conversion
└── inline/
    └── inline_handler.py # InlineQuery + ChosenInlineResult
```

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| Add command | `commands/*.py` | Export `router`, register in `__init__.py` |
| Change text processing | `messages/text_handler.py` | `handle_text_to_emoji()` |
| Fix inline mode | `inline/inline_handler.py` | Two-phase: placeholder → edit |
| Add middleware dependency | `__init__.py:setup_handlers()` | Register before routers |
| Change font selection logic | `messages/text_handler.py` | `get_user_font()` |

## UNIQUE PATTERNS

### Handler Signature
```python
async def handler(message: Message, session: AsyncSession, db_user: User, bot: Bot) -> None:
    # session: from DatabaseMiddleware (auto-commit/rollback)
    # db_user: from UserContextMiddleware (registered/get-or-create)
    # bot: injected by aiogram framework
```

### Middleware Registration Order
```python
# __init__.py - CRITICAL ORDER
dp.message.middleware(DatabaseMiddleware())    # First: provides session
dp.message.middleware(UserContextMiddleware()) # Second: uses session, provides db_user
dp.include_router(...)  # After middlewares
```

### Inline Mode Two-Phase Pattern
```python
@router.inline_query()
async def handle_inline_query(...):
    # Phase 1: Return placeholder with "Generating..." button
    await inline_query.answer([result_with_keyboard])

@router.chosen_inline_result()
async def handle_chosen_inline_result(...):
    # Phase 2: Edit message with actual custom emojis
    await bot.edit_message_text(inline_message_id=..., entities=...)
```

### Random Font Batch Processing
```python
# handlers/commands/random_font.py + inline/inline_handler.py
# Uses serial task queue for all sticker creations
# Batch operations: 1 DB query for all chars, batch render per font
# Tasks submitted to queue, processed one at a time globally
```

## NOTES

- **Router export**: Every module exports `router = Router()` at module level
- **Text limit**: 120 chars enforced via `MAX_TEXT_LENGTH` constant
- **Font priority**: user.preferred_font_id → first alphabetically
- **Inline cache**: `_query_cache` stores (text, is_random_font) temporarily