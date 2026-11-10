> **2026-10-20 新增：客服中心 + AI 绿色出行助手。** 普通用户/商户可创建客服工单，管理员可查看、回复与更新状态；所有对话保存在数据库中，用户只能查看自己的工单。AI 页面支持真实 OpenAI 兼容模型接口，必须配置服务端 API Key 和模型名称，否则明确显示“未配置”，右侧 FAQ 仍可使用。请先看 [《客服与AI功能操作指南》](客服与AI功能操作指南.md)。

> **2026-10-20 登录页面修复：** 修复登录成功后登录界面仍然显示（CSS `display:grid` 覆盖 `hidden`），并修复商户/管理员登录后退出按钮未显示。新增前端显示控制回归测试，浏览器 DOM 交互使用模拟 API 验证了三个角色的登录/退出显示状态。详见 `登录显示修复说明.md`。

# 青行 GreenGo — 城市绿色出行积分系统

可运行的软件工程课程项目：**需求分析 → UML → 迭代计划 → 后端/网页实现 → 数据库 → 测试 → 事件清算 → 部署说明**。

## 0. 已实现与未实现

居民可记录行程、筛选个人账本、兑换和退款。商户管理自己的品类、商品、库存和核销订单。管理员管理账号、客服工单及积分清算。平台还支持可选的大模型问答与独立事件处理进程。

**业务范围**：平台依据上报里程和当时生效的排放规则估算减排量及积分。商户维护商品、库存并处理兑换，管理员记录积分结算。网页使用原生 HTML/CSS/JS，后端支持 SQLite 和 MySQL 8。

## 1. 启动与首次管理员

需要 Python 3.10+。在 `green-commute` 目录创建并启用虚拟环境，然后安装依赖。

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell 使用 .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

正式启动设置 `ENVIRONMENT=production`、强随机 `JWT_SECRET` 和正式数据库的 `DATABASE_URL`。首次生成密钥可用 `python -c "import secrets; print(secrets.token_hex(32))"`。将结果保存到服务器的服务环境文件中，重启时沿用同一密钥。SQLite 默认路径为 `./green_commute.db`。

```bash
python -m scripts.upgrade_db
python -m scripts.create_admin site_admin
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

创建管理员时按提示输入并确认密码。居民通过网页注册，初始积分为 0。管理员登录后可在运营管理首页新增商户，在「账号管理」中编辑、重置密码、停用和恢复居民与商户。需要自动处理待办事件时，同一数据库运行一个 `python -m scripts.worker`。

打开 [本地网站](http://127.0.0.1:8000/) 或 [API 文档](http://127.0.0.1:8000/docs)。Windows Anaconda 使用方法见 [Anaconda 运行指南](Anaconda-运行指南.md)。

### 显式启用测试数据

仅在单独的测试数据库中设置 `SEED_DEMO_DATA=1` 和 `ENVIRONMENT=development`，然后启动服务。空数据库会创建 `resident`、`merchant`、`admin` 和测试商品。默认测试密码为 `Demo@123456`，可以通过 `DEMO_PASSWORD` 覆盖。正式模式始终跳过测试数据初始化。

### 升级现有部署

1. 停止网页服务与后台任务，备份数据库。SQLite 在停止写入后备份数据库及存在的 WAL 文件，MySQL 先导出备份。
2. 更新项目文件、安装本版依赖，再用**同一个正式数据库和服务环境**执行 `python -m scripts.upgrade_db`。该命令可以重复执行。它添加账号状态和会话版本，迁入每个商户已有商品品类，并补齐旧版账本和库存所需的字段与记录。
3. 对含旧演示数据的数据库，先创建并验证一个新管理员。使用「账号管理」停用确认属于演示用途的居民和商户，或为它们重置密码。对旧演示管理员，可运行 `python -m scripts.create_admin admin --reset-password` 更换凭据。停用和重置会让旧会话失效，关联历史记录保留。
4. 启动网页服务和后台任务，检查 `/api/health`，用不同角色登录验收。

已有 ECS 的 systemd 部署可用相同环境文件运行迁移。以下示例对应项目目录 `/opt/greengo`、服务账号 `greengo`，执行前先备份并更新发布目录及其虚拟环境。

```bash
systemctl stop greengo-worker.service greengo.service
systemd-run --wait --pipe --collect -p User=greengo -p WorkingDirectory=/opt/greengo -p EnvironmentFile=/etc/greengo.env /opt/greengo/.venv/bin/python -m scripts.upgrade_db
systemd-run --pty --collect -p User=greengo -p WorkingDirectory=/opt/greengo -p EnvironmentFile=/etc/greengo.env /opt/greengo/.venv/bin/python -m scripts.create_admin site_admin
systemctl start greengo.service greengo-worker.service
```

升级时已有可用正式管理员可跳过创建命令。公网入口通过 HTTPS 提供访问。

## 2. 一条完整业务链

1. 居民登录，进入「记录出行」，选择“公交”，输入 **30 公里**；系统按 180−70=110g/km 模拟节省 **3.3 kg CO₂e**，发放 **33积分**。
2. 进入积分商城，兑换“地铁单程体验券”花费 **12积分**；居民余额变为 **21**，库存减 1，形成订单和一笔 `-12` 的流水。
3. 商户登录，在工作台核销订单；管理员登录在运营管理中执行“完成清算”。
4. 查看居民积分账本：发放 +33，兑换 −12，余额 21。

**幂等保证**：同一用户、同一 `client_trip_id` 与相同业务数据多次提交仅创建一条行程；复用 ID 提交不同数据返回 HTTP 409；Outbox 重试不能重复记账。

## 3. 核心业务公式

设 `d` 为行程公里数。默认规则的汽车基准为 `180 g/km`，公交、地铁、骑行和步行的排放率分别为 70、40、0 和 0。每条行程按记录时生效的规则版本计算。

```
整数里程 m = d × 1000     # 输入最多2位小数
节约克数 saved_g = floor(m × (180 - E_mode) / 1000)
新增积分 points = floor(saved_g / 100)
可用积分 = sum(积分台账 delta)
```

采用整数米、整数克、整数积分，避免浮点精度影响财务式积分扣减。待核销订单可以退款，积分返还和库存回补均有流水记录。重复请求只记一次。

## 4. 运行自动化测试

```bash
python -m pytest -q tests
# 可选接口演练。在独立测试库启用 SEED_DEMO_DATA=1 后启动网页服务。
python scripts/demo_flow.py  # 默认连接本地8000端口
```

可选的浏览器截图脚本 `python scripts/capture_ui.py` 使用同一测试服务，需要安装 Playwright 和 Chromium。可通过 `DEMO_CHROMIUM_PATH` 指定本机的 Chromium 或 Edge 程序路径。

测试覆盖多账号隔离、会话撤销、商品与订单归属、品类迁移、日期筛选、库存及积分交易和客服与 AI 接口。默认使用独立临时 SQLite 数据库。也可将 `GREENGO_TEST_DATABASE_URL` 指向专门创建的 MySQL 测试库，库名须以 `greengo_test_` 开头。测试会重建该库的项目表。

## 5. 使用 MySQL + Docker Compose

需要 Docker Engine 和 Compose 插件。复制 `.env.example` 为 `.env`，填写强随机 `JWT_SECRET`、`MYSQL_ROOT_PASSWORD` 和 `MYSQL_PASSWORD`。已有部署保留原 MySQL 凭据和数据卷，先备份并停止 `web` 和 `worker`。

```bash
docker compose build web worker
docker compose run --rm web python -m scripts.upgrade_db
docker compose run --rm web python -m scripts.create_admin site_admin
docker compose up -d
```

`web` 默认绑定到本机 `127.0.0.1:8000`，可接入 HTTPS 反向代理。`worker` 轮询待处理事件。首次安装创建管理员一次，已有正式管理员的升级可跳过创建。数据库使用 `mysql_data` 持久卷。

可选的浏览器UI截图脚本需另外安装 `pip install -r requirements-ui.txt`、`playwright install chromium`，然后运行 `python scripts/capture_ui.py`。本制作环境存在浏览器URL访问限制，未生成真实浏览器截图。

## 6. 接口要点

完整接口见 `/docs` 和 `docs/OpenAPI.json`。私有接口使用 `Authorization: Bearer <token>`。

| 接口 | 访问与字段 |
|---|---|
| `POST /api/auth/register` | `username`、`password`。服务端固定居民角色，显示名使用用户名。 |
| `GET /api/trips/{id}`、`GET /api/redemptions/{id}` | 仅返回当前居民自己的记录。退款也核对订单归属。 |
| `POST /api/trips` | `client_trip_id` 由网页自动生成并在重试时复用。接口仍接受该字段，旧编号保留。 |
| `GET /api/wallet` | 可组合 `start_date`、`end_date`、`timezone`（IANA）和 `direction`（`all`、`income`、`expense`）。按本地日期筛选，结束日包含当天，正向退款属于收入。筛选后使用 `limit` 和 `before_id` 翻页，汇总按全量账本计算。 |
| `GET /api/products`、`GET /api/merchants` | 仅居民可访问，返回在售商品及启用商户。 |
| `GET/POST /api/merchant/categories` | 仅当前商户。创建传 `name`，去除首尾空白，同一商户重名返回 `409`。 |
| `/api/merchant/products`、`/api/merchant/orders` | 商品编辑、库存和订单核销均校验商户归属。商品接口的 `category` 继续接收品类名称，新增名称保存到本店品类。 |
| `POST /api/admin/merchants` | 仅管理员。传 `username`、`display_name`（店铺名称）和 `password`。 |
| `GET /api/admin/accounts` | 仅管理员。支持 `role`、`username`、`enabled` 筛选居民和商户。 |
| `PATCH /api/admin/accounts/{id}` | 仅管理员。更新 `username`、商户的 `display_name` 或 `enabled`，保留历史。 |
| `POST /api/admin/accounts/{id}/reset-password` | 仅管理员。传 `password`，重置后该账号已签发会话失效。 |

## 7. 项目结构

```text
app/
  main.py        API路由、RBAC与演示数据
  models.py      ORM实体与唯一约束
  services.py    核心规则、事务扣减与事件消费
  security.py    密码PBKDF2、JWT签名
  db.py          数据库与会话管理
  static/        完整可操作的响应式网页
scripts/
  worker.py      Outbox 消费进程
  demo_flow.py   实际API端到端演示记录
  capture_ui.py  浏览器截图脚本（受浏览器策略约束）
tests/          pytest 集成/业务规则测试
docs/           实验说明及新增模块设计、UML源文件、运行证据
Dockerfile, docker-compose.yml, .github/workflows/tests.yml
```

## 8. 诚信声明和协作约束

项目提供可复现的**技术交付样本**；**未伪造4—5人组队、GitHub远程协作记录、个人贡献、线上部署或教师验收签字**。Git本地提交由单一作者完成，仅用于展示版本控制结构；小组应按实际情况填写报告中的成员、真实 Git 链接、个人贡献与互评。

部分需求、模型、代码与测试内容通过 AI 协助构建；最终提交前每位组员需理解代码和设计，人工完成复核并在报告中修订真实使用记录。
