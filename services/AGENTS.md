# AGENTS.md - services/

**Generated:** 2026-04-02
**Commit:** 2762032
**Branch:** master

## OVERVIEW

Business logic services for sticker creation, font sync, image rendering, and user management.

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| Fix sticker creation flow | `sticker_service.py` | StickerService, StickerTaskQueue singleton |
| Debug task queue issues | `sticker_service.py` | `StickerTaskQueue._worker()` processes serially |
| Change rendering logic | `image_service.py` | ImageRenderer, ThreadPoolExecutor |
| Fix font sync bugs | `font_sync_service.py` | FontSyncService incremental merge |
| User registration | `user_service.py` | UserService wraps UserRepository |

## ANTI-PATTERNS

- **NEVER** bypass StickerTaskQueue for sticker creation - causes race conditions
- **NEVER** create stickers in parallel - breaks Telegram API, corrupts cache
- **NEVER** call ImageRenderer sync methods directly from async - blocks event loop
- **NEVER** forget to start queue at bot startup - `StickerTaskQueue.get_instance().start(bot, session_factory)`

## UNIQUE PATTERNS

### StickerTaskQueue (Global Serial Queue)
```python
# sticker_service.py - ONLY ONE sticker created at a time globally
class StickerTaskQueue:
    _instance: "StickerTaskQueue | None" = None  # Singleton
    
    async def submit(task: StickerCreationTask) -> str:
        await self._queue.put(task)
        await task.result_event.wait()  # Block until done
        return task.result
    
    async def _worker():  # Background task, processes FIFO serially
        task = await self._queue.get()
        emoji_id = await self._process_task(task, session)
        task.result = emoji_id
        task.result_event.set()  # Signal completion
```

### StickerCreationTask (Dataclass with Result Event)
```python
@dataclass
class StickerCreationTask:
    user_id: int
    character: str
    font_id: int
    font_path: Path
    image_bytes: bytes
    bot_username: str
    result_event: asyncio.Event = None  # Set in __post_init__
    result: str | None = None   # Filled by worker
    error: Exception | None = None  # Filled by worker on failure
```

### ImageRenderer (Thread Pool for Non-Blocking)
```python
# image_service.py - CPU-bound rendering offloaded to threads
class ImageRenderer:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._font_cache: dict[int, ImageFont.FreeTypeFont] = {}
    
    async def render_character(self, character: str, font_path: Path) -> bytes:
        font = self._get_font(font_path)  # Cached load
        return await loop.run_in_executor(self._executor, self._render_sync, character, font)
```

### FontSyncService (Incremental Merge)
```python
# font_sync_service.py - Add/update/reactivate/deactivate in one pass
class SyncResult(NamedTuple):
    added: int
    updated: int
    deactivated: int
    reactivated: int
    total_active: int

async def sync_fonts() -> SyncResult:
    disk_fonts = self._scan_font_files()
    db_fonts = await self.repo.get_all_fonts()
    # New: on disk, not in DB → insert
    # Existing: on disk, in DB → update name if changed
    # Reactivate: on disk, in DB but inactive → set active
    # Deactivate: not on disk, in DB → set inactive (soft delete)
```