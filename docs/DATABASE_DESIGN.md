# 数据库设计文档

## ER 图 (实体关系图)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   USER (用户)                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│ PK id                    INTEGER      内部用户ID                                │
│ UQ telegram_id           BIGINT       Telegram用户ID (业务主键)                  │
│    username              VARCHAR(32)  Telegram用户名                            │
│    full_name             VARCHAR(128) 用户全名                                   │
│    language              VARCHAR(2)   语言偏好 (zh/en)                          │
│ FK preferred_font_id     INTEGER      偏好字体ID (→ fonts.id)                   │
│    is_admin              BOOLEAN      是否管理员                                │
│    is_active             BOOLEAN      是否活跃                                  │
│    created_at            DATETIME     创建时间 (UTC)                            │
│    updated_at            DATETIME     更新时间 (UTC)                            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │ 1
                                    │
                                    │ N
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           STICKER_SET (贴纸包)                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│ PK id                    INTEGER      贴纸包ID                                  │
│ UQ pack_name             VARCHAR(64)  Telegram贴纸包名 (p{n}_by_{bot})           │
│    pack_index            INTEGER      包序号                                    │
│    sticker_count         INTEGER      当前贴纸数                                │
│    max_stickers          INTEGER      最大贴纸数 (120)                          │
│    pack_type             VARCHAR(20)  包类型 (custom_emoji)                     │
│    is_full               BOOLEAN      是否已满                                  │
│    is_active             BOOLEAN      是否活跃                                  │
│ FK created_by            INTEGER      创建者用户ID (→ users.id)                 │
│    created_at            DATETIME     创建时间 (UTC)                            │
│    updated_at            DATETIME     更新时间 (UTC)                            │
└─────────────────────────────────────────────────────────────────────────────────┘
       ▲ N
       │
       │ 1
┌──────┴──────────────────┐
│  FONT (字体)              │
├──────────────────────────┤
│ PK id                    │
│    name                  │
│    file_path             │
│    is_active             │
│    created_at            │
└──────────────────────────┘
       ▲ 1
       │
       │ N
┌──────┴──────────────────┐
│  CHARACTER_GLYPH (字形)   │
├──────────────────────────┤
│ PK id                    │
│ FK font_id               │
│    character             │
│    custom_emoji_id       │
│    file_id               │
│    emoji_list            │
│    created_at            │
└──────────────────────────┘
```

## 关系说明

| 关系 | 类型 | 描述 |
|------|------|------|
| User → StickerSet | 1:N | 一个用户可以创建多个贴纸包 |
| User → Font | 1:1 | 一个用户有一个偏好字体 |
| Font → CharacterGlyph | 1:N | 一个字体包含多个字形 |

---

## 索引设计

### 主键索引 (自动创建)
- 所有表: `id` PRIMARY KEY

### 唯一索引
| 表 | 字段 | 说明 |
|---|---|---|
| users | telegram_id | Telegram用户唯一标识 |
| sticker_sets | pack_name | 贴纸包名唯一 |

### 查询索引
| 表 | 索引名 | 字段 | 用途 |
|---|---|---|---|
| character_glyphs | ix_character_glyphs_font_id | font_id | 按字体查询字形 |
| users | ix_users_telegram_id | telegram_id | 按Telegram ID查询用户 |

---

## 字段详细说明

### User 表

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | INTEGER | 自增 | 主键 |
| telegram_id | INTEGER | 必填 | Telegram用户ID (唯一) |
| username | VARCHAR(32) | NULL | 用户名 |
| full_name | VARCHAR(128) | 必填 | 用户全名 |
| language | VARCHAR(2) | "zh" | 语言偏好 |
| preferred_font_id | INTEGER | NULL | 偏好字体ID |
| is_admin | BOOLEAN | False | 是否管理员 |
| is_active | BOOLEAN | True | 是否活跃 |
| created_at | DATETIME | UTC now | 创建时间 |
| updated_at | DATETIME | UTC now | 更新时间 |

### Font 表

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | INTEGER | 自增 | 主键 |
| name | VARCHAR(64) | 必填 | 字体显示名 |
| file_path | VARCHAR(256) | 必填 | 字体文件相对路径 |
| is_active | BOOLEAN | True | 是否活跃 |
| created_at | DATETIME | UTC now | 创建时间 |

### CharacterGlyph 表

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | INTEGER | 自增 | 主键 |
| font_id | INTEGER | 必填 | 字体ID (外键) |
| character | VARCHAR(1) | 必填 | 单个Unicode字符 |
| custom_emoji_id | VARCHAR(64) | 必填 | Telegram自定义emoji ID |
| file_id | VARCHAR(255) | 必填 | Telegram文件ID |
| emoji_list | VARCHAR(20) | "✏️" | 关联emoji列表 |
| created_at | DATETIME | UTC now | 创建时间 |

### StickerSet 表

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | INTEGER | 自增 | 主键 |
| pack_name | VARCHAR(64) | 必填 | 贴纸包名 (唯一) |
| pack_index | INTEGER | 必填 | 包序号 |
| sticker_count | INTEGER | 0 | 当前贴纸数 |
| max_stickers | INTEGER | 120 | 最大贴纸数 |
| pack_type | VARCHAR(20) | "custom_emoji" | 包类型 |
| is_full | BOOLEAN | False | 是否已满 |
| is_active | BOOLEAN | True | 是否活跃 |
| created_by | INTEGER | NULL | 创建者用户ID |
| created_at | DATETIME | UTC now | 创建时间 |
| updated_at | DATETIME | UTC now | 更新时间 |

---

## 并发控制

### 全局序列任务队列

```python
class StickerTaskQueue:
    """全局序列任务队列，确保只有一个贴纸创建操作在执行"""
    
    async def submit(task: StickerCreationTask) -> str:
        """提交任务并等待结果"""
        await self._queue.put(task)
        await task.result_event.wait()  # 阻塞直到完成
        return task.result
```

**优势**:
- 避免数据库层面的并发问题
- 简化缓存逻辑
- 确保贴纸包配额正确管理

---

## SQLite 优化配置

```python
# core/database.py
async_engine = create_async_engine(
    url,
    poolclass=NullPool,  # 无连接池，每次操作获取新连接
    connect_args={"timeout": 60.0}  # 60秒锁等待超时
)

# PRAGMA 设置
PRAGMA journal_mode=WAL      # 允许并发读
PRAGMA synchronous=NORMAL    # 平衡性能和持久性
PRAGMA cache_size=10000      # 10MB 缓存
PRAGMA mmap_size=30000000000 # 30GB 内存映射
PRAGMA busy_timeout=60000    # 60秒忙等待
```

---

## 技术栈整合

```
┌─────────────────────────────────────────┐
│           应用层 (aiogram)              │
│  handlers/commands/  handlers/messages/ │
├─────────────────────────────────────────┤
│           业务逻辑层 (services/)         │
│  StickerService  FontService  etc.      │
├─────────────────────────────────────────┤
│           数据访问层 (repositories/)     │
│  BaseRepository + 特定领域仓库          │
├─────────────────────────────────────────┤
│         ORM 层 (SQLModel)               │
│    SQLModel + SQLAlchemy 2.0            │
├─────────────────────────────────────────┤
│         数据库 (SQLite)                 │
│      aiosqlite (异步驱动)               │
│      WAL 模式 + 优化配置                │
└─────────────────────────────────────────┘
```

---

## 迁移管理

使用 Alembic 进行数据库迁移：

```bash
# 创建迁移
uv run alembic revision --autogenerate -m "description"

# 应用迁移
uv run alembic upgrade head

# 回滚迁移
uv run alembic downgrade -1
```

---

## 扩展建议

1. **监控**: 添加数据库查询性能监控
2. **备份**: 实现定期数据库备份策略
3. **缓存**: 考虑 Redis 缓存热门字形查询
