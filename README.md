# EkanjiBot - 文字转表情机器人

把任何文字转换成 Telegram 自定义表情贴纸！支持中文、日文、韩文、阿拉伯文、俄文、英文等任何语言 - 只要你的字体支持。

## 功能

- 🎨 **文字转表情** - 把任意文字变成精美的表情贴纸
- 🔤 **多字体支持** - 自动识别 `assets/fonts/` 目录下的所有字体
- 💾 **智能缓存** - 每个字符只需渲染一次，永久复用
- 📦 **自动管理** - 贴纸包满了自动创建新包（每包120个）
- 💬 **行内模式** - 在任意聊天输入 `@你的机器人 文字` 即可使用
- ✨ **保留格式** - 保留空格、换行等原始排版
- 🚫 **跳过表情** - 自动保留已有 Unicode 表情，不重复转换

## 快速开始

### 1. 安装依赖

需要 Python 3.12+ 和 [UV](https://github.com/astral-sh/uv) 包管理器：

```bash
# 克隆仓库
git clone https://github.com/yourusername/ekanji-bot.git
cd ekanji-bot

# 创建虚拟环境并安装依赖
uv venv --python 3.12
uv sync
```

### 2. 配置环境

复制示例配置文件并编辑：

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 Bot Token
```

`.env` 文件内容：

```
BOT_TOKEN=your_bot_token_here
DEBUG=false
```

获取 Bot Token：
1. 在 Telegram 搜索 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot` 创建新机器人
3. 复制获得的 Token 到 `.env` 文件

### 3. 添加字体

把字体文件放入 `assets/fonts/` 目录：

```
assets/
└── fonts/
    ├── 萝莉体第二版.ttf      # 中文字体
    ├── Arial.ttf            # 英文字体
    ├── Amiri.ttf            # 阿拉伯字体
    └── NotoSansCyrillic.ttf # 俄文字体
```

支持格式：`.ttf`, `.otf`, `.ttc`, `.woff`, `.woff2`

### 4. 启动机器人

```bash
# 直接运行
uv run bot.py

# 或使用 Docker
sudo sh start.sh
```

## 使用方法

### 基本命令

- `/start` - 开始使用，查看帮助
- `/fonts` - 查看可用字体列表

### 转换文字

直接发送任何文字即可：

```
你好世界
```

机器人会回复对应的表情贴纸：

```
🎨🎨 🎨🎨
```

（每个 🎨 实际是对应文字的自定义表情）

### 行内模式

在任意聊天窗口输入：

```
@你的机器人 你好
```

选择搜索结果即可发送表情。


## 许可证

MIT License
