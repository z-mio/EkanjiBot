# 数据库设计文档

## ER 图 (实体关系图)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   USER (用户)                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│ PK id                    INTEGER      内部用户ID                                │
│ UQ telegram_id           BIGINT       Telegram用户ID (业务主键)                  │
│    username              VARCHAR(32)  Telegram用户名                            │
│    first_name            VARCHAR(64)  名字                                      │
│    last_name             VARCHAR(64)  姓氏                                      │
│    language              ENUM         语言偏好 (zh_cn/en/ja/ko)                 │
│    is_premium            BOOLEAN      是否高级用户                               │
│    pack_quota            INTEGER      贴纸包配额                                 │
│    daily_request_limit   INTEGER      每日请求限制                               │
│    total_conversions     INTEGER      总转换次数                                 │
│    last_activity_at      DATETIME     最后活动时间                               │
│    created_at            DATETIME     创建时间                                   │
│    updated_at            DATETIME     更新时间                                   │
│    is_deleted            BOOLEAN      软删除标记                                 │
│    deleted_at            DATETIME     删除时间                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │ 1
                                    │
                                    │ N
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           STICKER_PACK (贴纸包)                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│ PK id                    INTEGER      贴纸包ID                                  │
│ FK owner_id              INTEGER      所有者用户ID (→ users.id)                 │
│ UQ telegram_name         VARCHAR(64)  Telegram贴纸包短名                          │
│    telegram_title        VARCHAR(128) 贴纸包标题                                │
│    pack_type             ENUM         类型 (static/animated/video)              │
│    capacity              INTEGER      总容量 (默认120)                         │
│    used_count            INTEGER      已使用位置                                 │
│    reserved_count        INTEGER      预留位置                                   │
│    status                ENUM         状态 (creating/active/full/archived)    │
│    telegram_set_name     VARCHAR(128) Telegram贴纸集名称                          │
│    last_synced_at        DATETIME     最后同步时间                               │
│    sync_version          INTEGER      同步版本号                                │
│    ...                   (时间戳和软删除字段)                                    │
└─────────────────────────────────────────────────────────────────────────────────┘
       ▲ N                                    ▲ N
       │                                      │
       │ 1                                    │ N
┌──────┴──────────────┐          ┌───────────┴──────────────────┐
│  FONT (字体)          │          │  STICKER_PLACEMENT (贴纸位置) │
├───────────────────────┤          ├──────────────────────────────┤
│ PK id                 │          │ PK id                        │
│ UQ code_name          │◄─────────│ FK pack_id                   │
│    display_name       │   N:M    │ FK glyph_id                  │
│    font_family        │  (关联表) │    position         INTEGER  │
│    status             │          │    sticker_file_id  VARCHAR  │
│    priority           │          │    custom_emoji_id    VARCHAR  │
│    glyph_count        │          │    is_active          BOOLEAN  │
│    ...                │          │    ...                       │
└───────────────────────┘          └───────────┬──────────────────┘
       ▲ 1                                     │ 1
       │                                       │
       │ N                                      │
┌──────┴──────────────┐                        │
│  GLYPH (字形/字库)   │                        │
├───────────────────────┤                        │
│ PK id                 │                        │
│ FK font_id            │                        │
│    character          │                        │
│ UQ (font_id, char)    │                        │
│    emoji_id           │                        │
│    category           │                        │
│    is_available       │                        │
│    usage_count        │                        │
│    ...                │                        │
└───────────────────────┘                        │
                                                 │
┌──────────────────────────────────────────────┴────────────────────┐
│                    USER_FONT_PREFERENCE (用户字体偏好)            │
├───────────────────────────────────────────────────────────────────┤
│ PK id                                                             │
│ FK user_id              (→ users.id)                              │
│ FK font_id              (→ fonts.id)                              │
│ UQ (user_id, font_id)                                             │
│    is_favorite          BOOLEAN                                   │
│    custom_font_size     INTEGER                                   │
│    custom_text_color    VARCHAR(7)                                │
│    custom_bg_color      VARCHAR(7)                                │
│    use_count            INTEGER                                   │
│    created_at           DATETIME                                  │
│    updated_at           DATETIME                                  │
└───────────────────────────────────────────────────────────────────┘
```

## 关联表

### font_pack_associations (字体-贴纸包多对多)
```
┌──────────────────────────────────────────┐
│ PK font_id  INTEGER → fonts.id           │
│ PK pack_id  INTEGER → sticker_packs.id   │
└──────────────────────────────────────────┘
```

## 辅助表

### USER_STATS (用户统计)
```
┌──────────────────────────────────────────┐
│ PK id                                   │
│ FK user_id     → users.id                │
│    stat_date   DATETIME                  │
│ UQ (user_id, stat_date)                  │
│    daily_conversions   INTEGER           │
│    daily_characters    INTEGER           │
│    stickers_created    INTEGER           │
└──────────────────────────────────────────┘
```

### GLYPH_VARIANT (字形变体)
```
┌──────────────────────────────────────────┐
│ PK id                                   │
│ FK glyph_id    → glyphs.id               │
│    variant_type   VARCHAR(32)            │
│ UQ (glyph_id, variant_type)              │
│    emoji_id       VARCHAR(128)           │
│    style_config   TEXT (JSON)            │
└──────────────────────────────────────────┘
```

### CHARACTER_MAPPING (字符映射)
```
┌──────────────────────────────────────────┐
│ PK id                                   │
│    source_char    VARCHAR(16)            │
│    target_char    VARCHAR(16)            │
│    mapping_type   VARCHAR(32)            │
│ UQ (source_char, mapping_type)           │
└──────────────────────────────────────────┘
```

### STICKER_PACK_QUOTA_LOG (配额变更日志)
```
┌──────────────────────────────────────────┐
│ PK id                                   │
│ FK pack_id     → sticker_packs.id        │
│    operation    VARCHAR(32)              │
│    count_change INTEGER                  │
│    used_count_before    INTEGER          │
│    used_count_after     INTEGER          │
│    reason       TEXT                     │
│    created_at   DATETIME                 │
└──────────────────────────────────────────┘
```

---

## 关系说明

| 关系 | 类型 | 描述 |
|------|------|------|
| User → StickerPack | 1:N | 一个用户可以拥有多个贴纸包 |
| User → UserFontPreference | 1:N | 一个用户可以有多个字体偏好设置 |
| Font → Glyph | 1:N | 一个字体包含多个字形 |
| Font → UserFontPreference | 1:N | 一个字体的多个用户偏好 |
| Font ↔ StickerPack | N:M | 字体与贴纸包多对多(通过关联表) |
| Glyph → StickerPlacement | 1:N | 一个字形可放置于多个贴纸包 |
| StickerPack → StickerPlacement | 1:N | 一个贴纸包包含多个贴纸位置 |
| StickerPack → QuotaLog | 1:N | 配额变更历史记录 |

---

## 索引设计

### 主键索引 (自动创建)
- 所有表: `id` PRIMARY KEY

### 唯一索引
| 表 | 字段 | 说明 |
|---|---|---|
| users | telegram_id | 业务主键 |
| fonts | code_name | 字体代码名 |
| sticker_packs | telegram_name | Telegram贴纸包名 |
| glyphs | (font_id, character) | 字体内字符唯一 |
| user_font_preferences | (user_id, font_id) | 用户字体偏好唯一 |
| sticker_placements | (pack_id, position) | 包内位置唯一 |
| sticker_placements | (pack_id, glyph_id) | 包内字形唯一 |

### 查询索引
| 表 | 索引名 | 字段 | 用途 |
|---|---|---|---|
| users | idx_user_language | language | 按语言筛选 |
| users | idx_user_premium | is_premium | 高级用户筛选 |
| users | idx_user_deleted | is_deleted | 软删除筛选 |
| fonts | idx_font_status | status | 可用字体查询 |
| fonts | idx_font_categories | supported_categories | 按分类筛选 |
| glyphs | idx_glyph_emoji | emoji_id | Emoji反向查找 |
| glyphs | idx_glyph_unicode | unicode_codepoint | 码点查询 |
| glyphs | idx_glyph_category | category | 字符分类筛选 |
| sticker_packs | idx_pack_owner | owner_id | 查询用户贴纸包 |
| sticker_packs | idx_pack_status | status | 状态筛选 |
| sticker_packs | idx_pack_type_status | (pack_type, status) | 组合筛选 |

---

## 约束条件

### CHECK 约束
```sql
-- 贴纸包容量检查
CHECK (used_count <= capacity)
CHECK (capacity <= 120)  -- Telegram限制

-- 字体大小范围
CHECK (min_font_size > 0)
CHECK (max_font_size <= 512)
CHECK (default_font_size BETWEEN min_font_size AND max_font_size)
```

### 外键约束
```sql
-- 级联删除配置
ON DELETE CASCADE: 用户删除时删除其贴纸包、偏好等
ON DELETE SET NULL: 安全删除，避免数据丢失
```

---

## 软删除设计

所有主要业务表都继承 `AuditMixin`，包含：

```python
is_deleted: bool = False   # 软删除标记
deleted_at: Optional[datetime] = None  # 删除时间
```

### 软删除的优点
1. **数据安全** - 误删可恢复
2. **审计追踪** - 保留历史记录
3. **外键完整性** - 避免级联删除问题
4. **数据分析** - 保留统计信息

### 查询过滤
```python
# 默认查询(自动过滤软删除)
query = select(Model).where(Model.is_deleted == False)

# 包含已删除
query = select(Model)  # 不添加过滤条件

# 仅查询已删除
query = select(Model).where(Model.is_deleted == True)
```

---

## 时间戳设计

### 自动管理字段
```python
created_at: datetime = Field(default_factory=datetime.utcnow)
updated_at: Optional[datetime] = Field(default=None, onupdate=datetime.utcnow)
```

### 时区处理
- 数据库存储: **UTC时间**
- 展示转换: 根据用户 `language` 偏好转换为本地时区

---

## 配额管理设计

### 贴纸包配额模型

```
┌─────────────┐    ┌──────────────────┐
│   capacity  │    │     120          │  总容量(Telegram限制)
├─────────────┤    ├──────────────────┤
│  used_count │    │      85          │  已使用
├─────────────┤    ├──────────────────┤
│reserved_count│   │       5          │  预留(批量操作)
├─────────────┤    ├──────────────────┤
│  available  │    │  120-85-5=30     │  可用
└─────────────┘    └──────────────────┘
```

### 配额检查流程
1. 用户请求添加贴纸
2. 查询 `available_count = capacity - used_count - reserved_count`
3. 如果 `available_count >= 需求数量`:
   - 增加 `reserved_count` (预留)
   - 执行操作
   - 更新 `used_count`
   - 减少 `reserved_count`
4. 记录到 `StickerPackQuotaLog`

### 并发控制
```python
sync_version: int  # 乐观锁

# 更新时检查版本
UPDATE sticker_packs 
SET used_count = used_count + 1, sync_version = sync_version + 1
WHERE id = :id AND sync_version = :current_version
```

---

## 用户表字段说明

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| telegram_id | BIGINT | 必填 | Telegram用户唯一标识 |
| username | VARCHAR(32) | NULL | @username |
| first_name | VARCHAR(64) | NULL | 名字 |
| last_name | VARCHAR(64) | NULL | 姓氏 |
| language | ENUM | 'zh_cn' | UI语言偏好 |
| is_premium | BOOLEAN | False | 高级用户标志 |
| pack_quota | INTEGER | 5 | 贴纸包配额 |
| daily_request_limit | INTEGER | 100 | 每日请求限制 |
| total_conversions | INTEGER | 0 | 累计转换次数 |
| last_activity_at | DATETIME | NULL | 最后活跃时间 |

---

## 技术栈整合

```
┌─────────────────────────────────────────┐
│           应用层 (aiogram)              │
├─────────────────────────────────────────┤
│           CRUD 层 (crud.py)             │
├─────────────────────────────────────────┤
│         会话管理 (engine.py)            │
│     async_sessionmaker + aiosqlite    │
├─────────────────────────────────────────┤
│         ORM 层 (SQLModel)               │
│    SQLModel + SQLAlchemy 2.0            │
├─────────────────────────────────────────┤
│         数据库 (SQLite)                 │
│      aiosqlite (异步驱动)               │
└─────────────────────────────────────────┘
```
