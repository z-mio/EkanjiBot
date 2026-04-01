# EkanjiBot

Convert any text into custom emoji stickers on Telegram. Supports all languages including Chinese, Japanese, Korean (CJK), Arabic, Cyrillic, Latin, and more - limited only by your fonts!

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.26%2B-green)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

## Features

- **Universal Text Support**: Convert text in any language to custom emoji stickers - Chinese, Japanese, Korean, Arabic, Cyrillic, Latin, emoji, symbols, and more
- **Multiple Fonts**: Auto-discover and manage fonts from `assets/fonts/` directory
- **Smart Caching**: Characters are rendered once per font and cached as custom emojis
- **Sticker Pack Management**: Automatic pack creation when capacity (120 stickers) is reached
- **Inline Mode**: Use `@YourBot text` in any chat to convert text inline
- **Preserve Layout**: Maintains original text formatting including spaces and line breaks
- **Unicode Emoji Support**: Automatically skips existing Unicode emojis

## Quick Start

### Prerequisites

- Python 3.12+
- [UV](https://github.com/astral-sh/uv) package manager
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Fonts in `assets/fonts/` directory (`.ttf`, `.otf`, `.ttc`)

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/ekanji-bot.git
cd ekanji-bot

# Create virtual environment and install dependencies
uv venv --python 3.12
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your BOT_TOKEN

# Run the bot
uv run bot.py
```

### Docker Deployment

```bash
# Using the provided script
sudo sh start.sh

# Or manually with docker-compose
docker-compose up -d
```

## Configuration

Create a `.env` file with the following variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram Bot API token from @BotFather |
| `BOT_PROXY` | No | Proxy URL for API requests (e.g., `socks5://host:port`) |
| `DEBUG` | No | Enable debug logging (`true` or `false`) |
| `DATABASE_URL` | No | SQLite database URL (default: `sqlite+aiosqlite:///./data/bot.db`) |

### Font Configuration

Place your font files in `assets/fonts/`. The bot supports any TrueType or OpenType font - add fonts for your specific languages:

```
assets/
└── fonts/
    ├── 萝莉体第二版.ttf          # Chinese/Japanese
    ├── NotoSansCJK.ttc           # CJK unified
    ├── Arial.ttf                 # Latin
    ├── DejaVuSans.ttf            # Latin extended
    ├── Amiri.ttf                 # Arabic
    └── NotoSansCyrillic.ttf      # Cyrillic
```

Supported font formats: `.ttf`, `.otf`, `.ttc`, `.woff`, `.woff2`

The bot will automatically:
- Discover fonts on startup
- Add new fonts to the database
- Deactivate missing fonts
- Set the first font alphabetically as default

## Usage

### Basic Commands

- `/start` - Welcome message and usage instructions
- `/fonts` - List available fonts
- `/lang` - Language settings (planned)

### Converting Text

Simply send any text message:

```
Hello World
```

The bot will reply with custom emoji stickers:

```
🎨🎨🎨🎨🎨 🎨🎨🎨🎨
```

*(Where each 🎨 is actually a custom emoji with the corresponding letter)*

### Inline Mode

Use the bot inline in any chat:

```
@YourBot Hello World
```

Then select from the results to send the emojis.

## Project Structure

```
ekhanji-bot/
├── bot.py                      # Main entry point
├── core/
│   ├── config.py              # Pydantic settings
│   └── database.py            # SQLAlchemy async setup
├── db/
│   ├── models/                # SQLModel definitions
│   │   ├── user.py
│   │   ├── font.py
│   │   ├── character_glyph.py
│   │   └── sticker_set.py
│   └── repositories/          # Data access layer
├── handlers/                  # Telegram message handlers
│   ├── commands/              # /start, /fonts
│   ├── messages/              # Text messages
│   └── inline/                # Inline queries
├── services/                  # Business logic
│   ├── sticker_service.py     # Emoji conversion
│   ├── image_service.py       # Pillow rendering
│   ├── font_sync_service.py   # Font management
│   └── user_service.py        # User operations
├── middlewares/               # aiogram middlewares
├── assets/
│   └── fonts/                 # Font files (gitignored)
├── pyproject.toml             # UV project config
├── docker-compose.yaml        # Docker orchestration
└── start.sh                   # Docker management script
```

## Development

### Code Quality

```bash
# Run linter
ruff check .

# Format code
ruff format .

# Type checking (optional)
mypy .
```

### Database Migrations

The bot uses SQLModel with automatic table creation. For manual migrations:

```bash
# Generate migration (if using Alembic)
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

## Technical Details

### Sticker Size Limits

- **Per Pack**: 120 custom emoji stickers
- **Packs Per User**: Unlimited
- **Sticker Size**: 100x100 pixels (WebP format)
- **Rendering**: Pillow with TrueType fonts

### UTF-16 Positioning

Telegram's API uses UTF-16 code units for entity offsets. The bot handles:
- Multi-byte Unicode characters (CJK, emoji)
- Surrogate pairs for emoji > U+FFFF
- Existing custom emoji preservation

### Concurrency

- **Image Rendering**: ThreadPoolExecutor (4 workers)
- **Sticker Uploads**: Semaphore (5 concurrent)
- **Pack Creation**: Per-user asyncio.Lock

## Troubleshooting

### No fonts available

```bash
# Check fonts directory
ls -la assets/fonts/

# Copy system fonts (Linux)
# For CJK: cp /usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc assets/fonts/
# For Latin: cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf assets/fonts/
```

### Database errors

```bash
# Reset database (will lose character cache)
rm -rf data/

# Note: Sticker packs in Telegram will be orphaned and recreated
```

### Sticker pack conflicts

If you see `STICKERSET_INVALID` errors, the bot will automatically:
1. Delete orphaned packs from Telegram
2. Create fresh packs at new indices
3. Re-render characters as needed

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

### Code Style

- Follow [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- Use type hints throughout
- Write docstrings for all public functions/classes
- Run `ruff check .` before committing

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- [aiogram](https://docs.aiogram.dev/) - Modern Telegram Bot API framework
- [SQLModel](https://sqlmodel.tiangolo.com/) - SQL databases in Python
- [Pillow](https://pillow.readthedocs.io/) - Python Imaging Library
- [UV](https://github.com/astral-sh/uv) - Fast Python package manager

---

**Note**: Font files are excluded from git due to copyright. Please use your own licensed fonts.
