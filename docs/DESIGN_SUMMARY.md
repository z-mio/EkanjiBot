# Telegram Bot 数据库设计总结

## 项目概述

为 EkanjiBot (Telegram 字体转贴纸 Bot) 设计的完整数据库架构。

## 数据库架构设计

### 核心表结构 (6个主表)

| 表名 | 用途 | 记录数预估 |
|------|------|-----------|
| **users** | 用户信息和偏好 | 1K-100K |
| **fonts** | 可用字体信息 | 10-50 |
| **glyphs** | 字符到emoji映射 | 10K-100K |
| **sticker_packs** | 贴纸包配额管理 | 100-10K |
| **sticker_placements** | 贴纸位置记录 | 10K-1M |
| **user_font_preferences** | 用户字体偏好 | 100-10K |

### 辅助表 (4个)

| 表名 | 用途 |
|------|------|
| **user_stats** | 用户每日统计 |
| **glyph_variants** | 字形变体(粗体/彩色等) |
| **character_mappings** | 字符标准化映射 |
| **sticker_pack_quota_logs** | 配额变更审计日志 |

## 最佳实践实现

### 1. 表关联设计

```
User (1) ────< (N) StickerPack
User (1) ────< (N) UserFontPreference
Font (1) ────< (N) Glyph
Font (1) ────< (N) UserFontPreference
Font (N) >────< (M) StickerPack (多对多关联表)
Glyph (1) ────< (N) StickerPlacement
StickerPack (1) ────< (N) StickerPlacement
```

**关键设计决策**:
- 使用 `font_pack_associations` 关联表处理字体与贴纸包的多对多关系
- 所有外键都配置 `ON DELETE CASCADE` 或 `ON DELETE SET NULL`
- 使用 SQLModel 的 `Relationship` 定义双向关系

### 2. 索引设计

**唯一索引 (业务约束)**:
- `users.telegram_id` - Telegram用户唯一标识
- `fonts.code_name` - 字体代码名
- `sticker_packs.telegram_name` - 贴纸包名
- `glyphs.(font_id, character)` - 字体内字符唯一

**查询优化索引**:
- `idx_glyph_emoji` - 通过 Custom Emoji ID 反向查找字形
- `idx_glyph_font_char` - 字体+字符组合查询(最常用)
- `idx_pack_owner` - 查询用户的所有贴纸包
- `idx_pack_status` - 按状态筛选可用贴纸包

### 3. 软删除实现

```python
class SoftDeleteMixin(SQLModel):
    is_deleted: bool = False    # 软删除标记
    deleted_at: Optional[datetime] = None  # 删除时间
```

**决策理由**:
- ✅ 防止误删导致数据丢失
- ✅ 保留历史记录用于审计
- ✅ 避免外键级联删除的数据不一致
- ✅ 支持用户数据恢复

**查询自动过滤**:
```python
# CRUDBase 自动添加过滤条件
if hasattr(self.model, "is_deleted"):
    query = query.where(self.model.is_deleted == False)
```

### 4. 时间戳设计

```python
class TimestampMixin(SQLModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(
        default=None,
        onupdate=datetime.utcnow
    )
```

**设计特点**:
- 使用 UTC 时间存储，避免时区问题
- `updated_at` 通过 SQLAlchemy `onupdate` 自动更新
- 支持 SQL `server_default` 确保数据库层面一致性

### 5. 贴纸包配额管理

**三层配额模型**:
```
capacity        = 120  (Telegram限制)
used_count      = 85  (已使用)
reserved_count  = 5   (预留/锁定)
available_count = 30  (可用 = 120-85-5)
```

**并发安全**:
```python
sync_version: int  # 乐观锁版本号

# 更新时检查版本，防止并发冲突
UPDATE sticker_packs 
SET used_count = used_count + 1, sync_version = sync_version + 1
WHERE id = :id AND sync_version = :current_version
```

**配额日志** (`sticker_pack_quota_logs`):
- 记录每次配额变更操作
- 用于审计、故障排查和数据恢复

### 6. 用户表字段设计

**核心字段**:
```python
telegram_id: int           # Telegram用户ID (业务主键)
username: str | None      # @用户名
language: UserLanguage    # UI语言偏好 (zh_cn/en/ja/ko)
is_premium: bool          # 高级用户标志
pack_quota: int           # 贴纸包配额 (默认5)
daily_request_limit: int  # 每日请求限制
```

**统计字段**:
```python
total_conversions: int           # 累计转换次数
last_activity_at: datetime      # 最后活跃时间
```

**设计考虑**:
- 分离 `user_stats` 表存储高频更新的统计数据
- 语言使用 ENUM 确保数据一致性
- 支持高级用户配额扩展

## 技术实现

### 目录结构
```
core/database/
├── __init__.py          # 模块导出
├── engine.py            # 数据库引擎和会话管理
├── crud.py              # 通用CRUD操作
├── init.py              # 初始化和种子数据
└── models/
    ├── __init__.py      # 模型导出
    ├── base.py          # 基类和混入类
    ├── enums.py         # 枚举类型和常量
    ├── user.py          # 用户模型
    ├── font.py          # 字体模型
    ├── glyph.py         # 字库模型
    └── sticker_pack.py  # 贴纸包模型
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
from core.database import (
    get_session, init_database, setup_database,
    user_crud, font_crud, glyph_crud, sticker_pack_crud
)
from core.database.models import User, Font, Glyph, StickerPack

# 初始化数据库
await setup_database()

# 获取会话
async with get_session() as session:
    # 创建用户
    user, created = await user_crud.get_or_create(
        session, telegram_id=123456,
        defaults={"username": "example"}
    )
    
    # 查询字体
    fonts = await font_crud.get_active(session)
    
    # 查询字形
    glyph = await glyph_crud.get_by_font_and_char(
        session, font_id=1, character="中"
    )
    
    # 查询用户贴纸包
    packs = await sticker_pack_crud.get_by_owner(
        session, owner_id=user.id
    )
```

## 性能优化

### 1. 连接池配置
```python
create_async_engine(
    "sqlite+aiosqlite:///data/bot.db",
    poolclass=NullPool,  # SQLite异步推荐
)
```

### 2. 关系加载策略
```python
# 使用 selectin 加载避免 N+1 问题
sticker_packs: List["StickerPack"] = Relationship(
    back_populates="owner",
    sa_relationship_kwargs={"lazy": "selectin"}
)
```

### 3. 批量操作
```python
# 批量创建
await crud.create_multi(session, objs_in=[obj1, obj2, ...])
```

## 扩展建议

1. **缓存层**: 使用 Redis 缓存热门字形查询
2. **读写分离**: 如果数据量大，考虑主从复制
3. **分表**: 当 `glyphs` 表超过百万级时，可按字体分表
4. **全文搜索**: 添加字体搜索功能时使用 SQLite FTS5

## 总结

本设计满足以下需求:
- ✅ 完整的字体-字形-emoji映射存储
- ✅ 用户贴纸包配额管理
- ✅ 用户语言偏好设置
- ✅ 软删除和数据安全
- ✅ 异步高性能访问
- ✅ 清晰的表关系和约束
