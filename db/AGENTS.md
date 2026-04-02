# AGENTS.md - db/ (Database Layer)

**Generated:** 2026-04-02
**Commit:** 2762032
**Branch:** master

## OVERVIEW

Repository pattern implementation with SQLModel ORM. Generic BaseRepository + domain-specific repositories.

## STRUCTURE

```
db/
├── __init__.py          # Exports: User, Font, CharacterGlyph, StickerSet
├── models/              # SQLModel table definitions
│   ├── base.py          # CreatedAtField, UpdatedAtField helpers
│   ├── user.py          # User: telegram_id, preferences, relationships
│   ├── font.py          # Font: name, file_path, is_active
│   ├── character_glyph.py  # CharacterGlyph: character → emoji mapping
│   └── sticker_set.py   # StickerSet: pack quota management (120 stickers)
└── repositories/        # Data access layer
    ├── base.py          # BaseRepository[ModelType]: CRUD generic
    ├── user_repo.py     # get_by_telegram_id, get_or_create
    ├── font_repo.py     # get_active_fonts, deactivate_fonts_not_in
    ├── character_glyph_repo.py  # get_by_character_and_font, batch get
    └── sticker_set_repo.py  # get_available_pack, increment_with_retry
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add new model | `db/models/` + export in `db/models/__init__.py` |
| Add new query | `db/repositories/<model>_repo.py` |
| Change field defaults | `db/models/base.py` |
| Extend CRUD | Inherit from `BaseRepository[ModelType]` |
| Fix race condition | `character_glyph_repo.py:create_or_get()` |
| Fix DB lock retries | `sticker_set_repo.py:increment_sticker_count_with_retry()` |

## UNIQUE PATTERNS

### Generic Repository
```python
class BaseRepository[ModelType]:
    # CRUD: get_by_id, get_all, create, update, delete
```

### Field Helpers
```python
created_at: datetime = CreatedAtField()   # UTC now
updated_at: datetime = UpdatedAtField()   # UTC now + onupdate
```

### Race Condition Handling
```python
# CharacterGlyphRepository.create_or_get() - check-then-create
# Returns existing instead of failing on duplicate character+font
# Note: With global serial task queue, race conditions are minimized
```

### Batch Optimization
```python
# CharacterGlyphRepository.get_by_characters_and_fonts()
# N queries → 1 query with OR conditions, dedup by oldest id
```

### SQLite Lock Retry
```python
# StickerSetRepository.increment_sticker_count_with_retry()
# Atomic UPDATE ... RETURNING + exponential backoff on lock
```

### Soft Delete Pattern
```python
# FontRepository - activate/deactivate instead of hard delete
```