# 源纪元 · 岸线侵入  —  网页部署指南

## 项目架构

```
浏览器 ──HTTP──► Netlify / 静态服务 (前端)  ： web/explorer/（纯 HTML/CSS/JS）
             └──► Python 后端 API (8787端口) ： game/ + narrative_ai/（JSON API）
```

- **前端**：纯静态单页应用，零框架依赖，Canvas 渲染等距大地图
- **后端**：Python 标准库，ThreadingHTTPServer，OpenAI 兼容 API 调用
- **依赖**：仅需 **Python >= 3.10**，无第三方包

> 前后端分离部署。前端托管在 Netlify，后端需部署到支持 Python 的服务器。

---

## 方案 A：Netlify（前端）+ Railway / Render（后端）★ 推荐

这是推荐的公网部署方案。

### 第 1 步：部署后端 API

后端需要在支持 Python 并可长期运行的平台上部署。

**Railway（推荐，免费额度充足）**

1. 访问 [railway.app](https://railway.app)，用 GitHub 登录
2. 点击 **New Project → Deploy from GitHub repo**
3. 选择本仓库
4. 在 Railway 项目设置中添加环境变量：

| 变量 | 值 |
|------|-----|
| `NARRATIVE_AI_API_KEY` | `sk-你的API密钥` |
| `NARRATIVE_AI_BASE_URL` | `http://35.220.164.252:3888` |
| `NARRATIVE_AI_MODEL` | `gpt-4o-mini` |
| `GAME_API_HOST` | `0.0.0.0` |
| `GAME_API_PORT` | `8787` |
| `GAME_DEBUG_API` | `0` |

5. Railway 会自动检测 Python 项目并启动。记下分配的域名，如 `source-epoch.up.railway.app`

**Render（备选）**

1. 访问 [render.com](https://render.com)，创建 Web Service
2. 连接仓库，设置：
   - **Build Command**: `echo 'no build'`
   - **Start Command**: `python -u -m game`
3. 添加同样的环境变量，记下分配的域名

### 第 2 步：部署前端到 Netlify

**方式 1：通过 Netlify 网站拖拽部署**

1. 打开 `web/explorer/index.html`
2. 修改 API 配置（第 63-67 行），取消注释并填入后端地址：
   ```javascript
   window.__GAME_API_BASE__ = "https://source-epoch.up.railway.app";
   ```
3. 将 **整个 `web/explorer/` 文件夹** 拖入 [app.netlify.com/drop](https://app.netlify.com/drop)

**方式 2：通过 Git + Netlify 自动部署**

1. 在 `web/explorer/index.html` 中填入后端 API 地址（同上）
2. 提交代码到 GitHub
3. 在 Netlify 后台：**Add new site → Import an existing project → GitHub**
4. 配置部署设置：
   - **Base directory**: 留空
   - **Build command**: 留空（无需构建）
   - **Publish directory**: `web/explorer/`
5. 点击 Deploy

> 部署配置已写入项目根目录的 `netlify.toml`，Netlify 会自动读取。

### 第 3 步：验证

1. 浏览器打开 Netlify 分配的域名（如 `xxx.netlify.app`）
2. 应能看到大地图界面
3. 如提示无法连接，检查：
   - 后端 Railway/Render 服务是否在运行
   - 前端 `index.html` 中的 `__GAME_API_BASE__` 地址是否正确
   - 后端 API 端口是否对外开放（Railway 默认公网可访问）

> 也可通过 URL 参数临时指定后端：`https://你的域名?api=https://后端地址`

### 切换后端地址（无需重新部署）

如果后端地址变动，无需重新部署前端，直接通过 URL 参数指定：

```
https://xxx.netlify.app?api=https://新的后端地址
```

---

## 方案 B：本地部署（开发 / 局域网测试）

### 1. 环境准备
```bash
python --version   # 需要 >= 3.10
```

### 2. 配置
```bash
cp .env.example .env
# 编辑 .env 填入 NARRATIVE_AI_API_KEY
```

### 3. 启动
- **一键启动**：双击 `start_server.cmd` 或运行 `start_server.ps1`
- **分别启动**：
  - 终端 1：`python -u -m game`（端口 8787）
  - 终端 2：`python -m http.server 8080 --bind 127.0.0.1`（端口 8080）

### 4. 访问
浏览器打开：**http://127.0.0.1:8080/web/explorer/**

---

## 方案 C：Nginx 反向代理（单台 Linux 服务器）

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /opt/source-epoch/web/explorer/;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8787;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 120s;
    }
}
```

Systemd 服务 `/etc/systemd/system/source-epoch-api.service`：
```ini
[Unit]
Description=Source Epoch Incursion - Game API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/source-epoch
Environment=NARRATIVE_AI_API_KEY=sk-xxxxx
Environment=NARRATIVE_AI_BASE_URL=http://35.220.164.252:3888
Environment=NARRATIVE_AI_MODEL=gpt-4o-mini
Environment=GAME_DEBUG_API=0
Environment=GAME_API_HOST=127.0.0.1
Environment=GAME_API_PORT=8787
ExecStart=/usr/bin/python3 -u -m game
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now source-epoch-api
sudo systemctl reload nginx
```

> 此方案下前端可直接使用 `/api/*` 路径（同域），无需配置 `__GAME_API_BASE__`。

---

## 方案 D：Docker 部署

```dockerfile
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY game/ ./game/
COPY narrative_ai/ ./narrative_ai/
COPY web/ ./web/
COPY index.html ./
ENV GAME_API_HOST=0.0.0.0
ENV GAME_API_PORT=8787
ENV GAME_DEBUG_API=0
EXPOSE 8787
CMD ["python", "-u", "-m", "game"]
```

```bash
docker build -t source-epoch-api .
docker run -d --name source-epoch-api \
  -p 8787:8787 \
  -e NARRATIVE_AI_API_KEY=sk-xxxxx \
  -e NARRATIVE_AI_BASE_URL=http://35.220.164.252:3888 \
  source-epoch-api
```

---

## 目录结构（部署视角）

```
项目根/
├── netlify.toml           # Netlify 部署配置
├── .env.example           # 配置模板
├── requirements.txt       # Python 依赖（纯标准库）
├── start_server.cmd       # 本地一键启动 (CMD)
├── start_server.ps1       # 本地一键启动 (PowerShell)
│
├── game/                  # ★ 后端核心（Python 游戏逻辑 + HTTP API）
├── narrative_ai/          # ★ AI 叙事引擎（OpenAI 兼容客户端）
├── web/explorer/          # ★ 前端（纯静态）→ 部署到 Netlify
│   ├── index.html         #   入口页（在此配置后端 API 地址）
│   ├── main.js            #   主逻辑
│   ├── styles.css         #   样式
│   ├── _redirects         #   Netlify SPA 路由规则
│   └── assets/            #   图片资源
│
├── docs/                  # 设计文档（参考用，不影响运行）
├── raw_doc/               # 原始设计稿
├── tools/                 # 开发工具
└── assets/                # 生成资产源文件
```

> ★ 标记的目录为**运行必需**。

---

## API 地址配置优先级

前端按以下优先级确定后端 API 地址：

1. **URL 查询参数** `?api=https://地址` — 最高优先级，适合临时切换
2. **`window.__GAME_API_BASE__`** — 在 `index.html` 中配置，适合固定部署
3. **默认值** `http://127.0.0.1:8787` — 本地开发

---

## 常见问题

**Q: Netlify 页面打开后提示"无法连接游戏服务器"？**
A: 后端 Python API 需要单独部署（Railway/Render/VPS）。确认后端服务正常运行，且 `index.html` 中的 `__GAME_API_BASE__` 地址正确。

**Q: AI 对话不回复？**
A: 检查后端服务的 `NARRATIVE_AI_API_KEY` 和 `NARRATIVE_AI_BASE_URL` 环境变量。可设 `NARRATIVE_AI_DRY_RUN=1` 测试离线模式。

**Q: CORS 跨域错误？**
A: 后端已在所有响应中设置 `Access-Control-Allow-Origin: *`，理论无跨域问题。如仍有问题，检查后端是否正常返回 CORS 头。

**Q: 如何更新已部署的前端？**
A: 如果通过 Git 连接，推送代码即可自动部署。如果手动拖拽部署，重新拖入更新后的 `web/explorer/` 文件夹。

**Q: 可以纯前端部署，不需要后端吗？**
A: 不可以。游戏剧情逻辑、NPC 对话、AI 叙事生成都依赖 Python 后端。但可以设置 `NARRATIVE_AI_DRY_RUN=1` 使用离线占位文本测试。
