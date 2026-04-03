# Telegram Bot 数据库设计总结

## 项目概述

为 EkanjiBot (Telegram 字体转贴纸 Bot) 设计的数据库架构。

## 数据库架构设计

### 核心表结构 (4个主表)

| 表名 | 用途 | 记录数预估 |
|------|------|-----------|
| **users** | 用户信息和偏好 | 1K-100K |
| **fonts** | 可用字体信息 | 10-50 |
| **character_glyphs** | 字符到emoji映射 | 10K-100K |
| **sticker_sets** | 贴纸包配额管理 | 100-10K |

## 表关联设计

```
User (1) ────< (N) StickerSet
User (1) ──────── (1) Font (preference)
Font (1) ────< (N) CharacterGlyph
```

**关键设计决策**:
- 使用 `preferred_font_id` 外键关联用户偏好字体
- `CharacterGlyph` 使用 `font_id` 和 `character` 的组合确保唯一性
- `StickerSet` 使用 `created_by` 外键记录创建者
- 所有表都使用 `created_at` 时间戳
- 部分表使用 `updated_at` 自动更新

## 索引设计

**唯一索引 (业务约束)**:
- `users.telegram_id` - Telegram用户唯一标识
- `character_glyphs.(font_id, character)` - 字体内字符唯一（通过应用逻辑保证）
- `sticker_sets.pack_name` - 贴纸包名

**查询优化索引**:
- `ix_character_glyphs_font_id` - 按字体查询字形
- `ix_users_telegram_id` - 按Telegram ID查询用户

## 时间戳设计

```python
created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
updated_at: datetime = Field(
    default_factory=lambda: datetime.now(UTC),
    sa_column_kwargs={"onupdate": func.now()},
)
```

**设计特点**:
- 使用 UTC 时间存储，避免时区问题
- `updated_at` 通过 SQLAlchemy `onupdate` 自动更新

## 贴纸包配额管理

**配额模型**:
```
max_stickers = 120  (Telegram限制)
sticker_count = 85  (已使用)
available = 120 - 85 = 35  (可用)
```

**并发控制**:
- 使用全局序列任务队列（`StickerTaskQueue`）确保只有一个贴纸创建操作在执行
- 避免了数据库层面的并发问题

## 技术实现

### 目录结构
```
db/
├── __init__.py          # 模块导出
├── models/              # SQLModel 表定义
│   ├── __init__.py      # 模型导出
│   ├── base.py          # CreatedAtField, UpdatedAtField 工厂
│   ├── user.py          # 用户模型
│   ├── font.py          # 字体模型
│   ├── character_glyph.py  # 字形模型
│   └── sticker_set.py   # 贴纸包模型
└── repositories/        # 数据访问层
    ├── base.py          # 通用 CRUD 操作
    ├── user_repo.py     # 用户查询
    ├── font_repo.py     # 字体查询
    ├── character_glyph_repo.py  # 字形查询
    └── sticker_set_repo.py  # 贴纸包查询
```

### 依赖配置 (pyproject.toml)
```toml
dependencies = [
    "aiosqlite>=0.21.0",            # 异步SQLite驱动
    "sqlalchemy[asyncio]>=2.0.39",  # 异步SQLAlchemy
    "sqlmodel>=0.0.24",             # SQLModel ORM
    # ... 其他依赖
]
```

### 使用示例

```python
from db.models import User, Font, CharacterGlyph, StickerSet
from db.repositories import UserRepository, FontRepository

# 获取或创建用户
user_repo = UserRepository(session)
user = await user_repo.get_or_create_user(
    telegram_id=123456,
    username="example",
    full_name="Example User"
)

# 查询可用字体
font_repo = FontRepository(session)
fonts = await font_repo.get_active_fonts()

# 查询字形缓存
glyph_repo = CharacterGlyphRepository(session)
glyph = await glyph_repo.get_by_character_and_font(
    character="中", font_id=1
)
```

## 性能优化

### 1. 连接池配置
```python
create_async_engine(
    "sqlite+aiosqlite:///data/bot.db",
    poolclass=NullPool,  # SQLite异步推荐
    connect_args={"timeout": 60.0}
)
```

### 2. SQLite 优化
```python
# PRAGMA 设置
PRAGMA journal_mode=WAL      # 允许并发读
PRAGMA synchronous=NORMAL    # 平衡性能和持久性
PRAGMA cache_size=10000      # 10MB 缓存
PRAGMA busy_timeout=60000    # 60秒锁等待
```

### 3. 批量查询
```python
# 批量获取字形 - N个查询 → 1个查询
cache_map = await glyph_repo.get_by_characters_and_fonts(char_font_pairs)
```

## 扩展建议

1. **缓存层**: 使用 Redis 缓存热门字形查询
2. **监控**: 添加数据库查询性能监控
3. **备份**: 实现定期数据库备份策略

## 总结

本设计满足以下需求:
- ✅ 字体-字形-emoji映射存储
- ✅ 用户偏好管理
- ✅ 贴纸包配额管理
- ✅ 异步高性能访问
- ✅ 清晰的表关系和约束
- ✅ 全局序列任务队列避免并发问题
