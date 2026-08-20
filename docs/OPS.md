# nanobot 网关运维手册（个人部署）

> 适用环境：Mac mini（darwin arm64），launchd 托管的个人部署。最后更新：2026-08-20

## 1. 服务概览

| 项目 | 值 |
|---|---|
| 服务 | launchd LaunchAgent `ai.nanobot.gateway`（plist：`~/Library/LaunchAgents/ai.nanobot.gateway.plist`） |
| 代码 | `/Users/sambazhu/nanobot`（venv editable 安装，**跑的是工作区当前检出分支**） |
| 生产分支 | `deploy`（集成分支；`main` 只跟踪 upstream，功能在 `feat/*` 开发） |
| 健康检查 | `http://127.0.0.1:18790/health` → `{"status":"ok"}` |
| WebUI | `http://127.0.0.1:8765` |
| 配置 | `~/.nanobot/config.json`（改动后需重启网关生效） |
| 数据目录 | `~/.nanobot/`（logs/、run/、会话数据） |
| 自愈 | RunAtLoad（登录自启）+ KeepAlive（异常退出自动拉起） |

## 2. 日常巡检（三条命令）

```bash
# ① 进程状态：第一列是 PID，第二列是上次退出码（0 正常）
launchctl list | grep nanobot

# ② 健康检查
curl -s http://127.0.0.1:18790/health

# ③ 运行日志：心跳 cron 每 30 分钟一条 = 活性信号
tail -20 ~/.nanobot/logs/nanobot-gateway.launchd.err.log
```

## 3. 常用操作

```bash
# 重启（中断数秒，KeepAlive 自动拉起）
launchctl kickstart -k gui/$(id -u)/ai.nanobot.gateway

# 彻底停止（卸载服务，不再自动拉起）
launchctl bootout gui/$(id -u)/ai.nanobot.gateway

# 重新启动已停止的服务
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.nanobot.gateway.plist

# 实时看日志（banner 在 .log，运行明细/报错在 .err.log）
tail -f ~/.nanobot/logs/nanobot-gateway.launchd.err.log
```

## 4. 分支与发布（⚠️ 重点）

网关进程加载的是 `/Users/sambazhu/nanobot` 工作区**当前检出的分支**。**切换分支后必须重启网关**，否则进程仍运行旧分支代码——磁盘上文件变了，进程内懒加载的模块会找不到。

> 案例：2026-08-19 微信回复故障。8-15 网关以 `deploy` 启动，之后工作区切回 `main`，
> `dashscope_provider.py` 从磁盘消失，微信消息触发 `ModuleNotFoundError`。切回 deploy + 重启恢复。

发布流程：

```bash
git fetch upstream && git checkout main && git merge --ff-only upstream/main   # main 跟进 upstream
git checkout deploy && git merge main        # 合入集成分支，解决冲突后跑测试
pytest tests/providers/ && ruff check nanobot/
launchctl kickstart -k gui/$(id -u)/ai.nanobot.gateway   # 重启生效
curl -s http://127.0.0.1:18790/health                    # 验证
```

## 5. 日志文件说明

| 文件（`~/.nanobot/logs/`） | 内容 |
|---|---|
| `nanobot-gateway.launchd.err.log` | **主要看这个**：运行明细（INFO cron/消息处理）+ 错误堆栈 |
| `nanobot-gateway.launchd.log` | 启动 banner（版本、渠道、端口、定时任务） |
| `gateway.log` / `gateway.*.log` | CLI 后台方式启动时的日志，当前部署未使用 |

## 6. 故障排查速查

| 现象 | 排查 |
|---|---|
| `/health` 不通 | `launchctl list \| grep nanobot` 看 PID 与退出码 → `tail` err 日志找 Traceback |
| 微信不回复 | err 日志 grep `Traceback`；若是 `ModuleNotFoundError` 多为切分支未重启（见第 4 节） |
| `nanobot gateway status` 显示 not_started | **正常现象**，该命令只认 CLI 后台实例的状态文件，launchd 部署不写它，勿被误导 |
| 端口被占用 | 多为旧实例未退：`ps aux \| grep nanobot` 找 PID，kickstart 重启即可 |
| 重启机器后网关没起 | 本服务为用户级 LaunchAgent，需登录桌面后才会启动；需无人值守运行改为 LaunchDaemon |

## 7. 注意事项

- `~/.nanobot/config.json` 与日志中含 API key 明文，外传日志前先清理
- WebUI 提示 "source is newer than bundled build" 时，跑 `cd webui && bun run build` 后重启即可（不影响运行）
