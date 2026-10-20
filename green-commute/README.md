> **2026-10-20 新增：客服中心 + AI 绿色出行助手。** 普通用户/商户可创建客服工单，管理员可查看、回复与更新状态；所有对话保存在数据库中，用户只能查看自己的工单。AI 页面支持真实 OpenAI 兼容模型接口，必须配置服务端 API Key 和模型名称，否则明确显示“未配置”，右侧 FAQ 仍可使用。请先看 [《客服与AI功能操作指南》](客服与AI功能操作指南.md)。

> **2026-10-20 登录页面修复：** 修复登录成功后登录界面仍然显示（CSS `display:grid` 覆盖 `hidden`），并修复商户/管理员登录后退出按钮未显示。新增前端显示控制回归测试，浏览器 DOM 交互使用模拟 API 验证了三个角色的登录/退出显示状态。详见 `登录显示修复说明.md`。

# 青行 GreenGo — 城市绿色出行积分系统

可运行的软件工程课程项目：**需求分析 → UML → 迭代计划 → 后端/网页实现 → 数据库 → 测试 → 事件清算 → 部署说明**。

## 0. 已实现与未实现

已实现：客服工单、管理员客服回复、可选真实大模型问答与本地常见问题库、注册/登录、居民/商户/管理员角色、公交/地铁/骑行/步行模拟上报、减排模拟系数、积分发放与唯一账本、重复行程幂等、积分商城、库存及积分原子扣减、订单履约、运营清算、事务型 Outbox 事件、单独事件处理进程、响应式网页、OpenAPI文档、自动化测试。

**边界**：没有连接真实公交/地铁 GPS 或支付清算系统；碳排放因子是教学模拟值，不是官方认可的碳减排量；商品均为演示商品，不可线下兑付。网页采用原生 HTML/CSS/JS 的无构建依赖 SPA；FastAPI 为现代 Web API 框架。SQLite 实现零配置试运行，`docker compose` 示例切换 MySQL 8。

## 1A. Windows Anaconda Prompt 一站式启动（优先推荐）

如果你已经安装 Anaconda，**所有命令都可在 Anaconda Prompt 中执行**；完整步骤见 [`Anaconda-运行指南.md`](Anaconda-运行指南.md)。首次进入项目根目录后：

```bat
conda env create -f environment.yml
conda activate greengo
python -m pytest -q tests
set "JWT_SECRET=greengo-course-local-only-change-before-deployment"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`。这是优先的 Anaconda 运行方式；下面的通用 Python 虚拟环境命令仅供非 Anaconda 用户参考。

## 1. 本地立即启动（Python 3.10+）

```bash
cd green-commute
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
# Windows PowerShell: $env:JWT_SECRET="change-this-to-a-long-random-secret"
# Linux/macOS:
export JWT_SECRET="change-this-to-a-long-random-secret"
uvicorn app.main:app --reload
```

浏览器打开 **http://127.0.0.1:8000/**，API文档 **http://127.0.0.1:8000/docs**。如果不存在数据库，首次启动会自动创建 `green_commute.db` 与演示数据；交付压缩包中另含一份已执行过业务链的演示数据库，删除后可重置。无需 Node / 前端编译。

| 角色 | 用户名 | 初始密码 | 功能 |
|---|---|---|---|
| 居民 | `resident` | `Demo@123456` | 行程、积分、商品兑换 |
| 商户 | `merchant` | `Demo@123456` | 发布商品、兑换订单核销 |
| 平台管理员 | `admin` | `Demo@123456` | 汇总统计、事件重试、清算 |

演示账号只用于本地或隔离的教学环境，**严禁将固定演示密码和默认 JWT 秘钥用于公网**。生产方案须关闭演示账户、配置密钥、HTTPS、审计和防刷机制。

## 2. 一条完整业务链

1. 居民登录，进入「记录出行」，选择“公交”，输入 **30 公里**；系统按 180−70=110g/km 模拟节省 **3.3 kg CO₂e**，发放 **33积分**。
2. 进入积分商城，兑换“地铁单程体验券”花费 **12积分**；居民余额变为 **21**，库存减 1，形成订单和一笔 `-12` 的流水。
3. 商户登录，在工作台核销订单；管理员登录在运营管理中执行“完成清算”。
4. 查看居民积分账本：发放 +33，兑换 −12，余额 21。

**幂等保证**：同一用户、同一 `client_trip_id` 与相同业务数据多次提交仅创建一条行程；复用 ID 提交不同数据返回 HTTP 409；Outbox 重试不能重复记账。

## 3. 核心业务公式

设 `d` 为行程公里数，`E_car = 180 g/km` 为模拟汽车基准，出行排放率公交70、地铁40、骑行/步行0（均为教学参数）。

```
整数里程 m = d × 1000     # 输入最多2位小数
节约克数 saved_g = floor(m × (180 - E_mode) / 1000)
新增积分 points = floor(saved_g / 100)
可用积分 = sum(积分台账 delta)
```

采用整数米、整数克、整数积分，避免浮点精度影响财务式积分扣减。暂不支持重复退单、积分有效期和碳核证。

## 4. 运行自动化测试

```bash
pytest -q tests/
# 可选人工接口复测：先启动 uvicorn，再运行
python scripts/demo_flow.py  # 默认连接本地8000端口
```

当前自动测试包含27个用例（新增8个客服/AI用例）（原业务测试16个，前端显示测试3个，客服/大模型测试8个），覆盖：健康检查、凭证认证、居民注册、距离/积分边界、发放和台账、幂等性、非法输入、积分不足、库存不足、角色访问控制、用户隔离、事件重复投递、商户履约与清算、商品上架、双请求竞争库存。每次测试在独立临时 SQLite 数据库重建表，不污染演示数据。

## 5. 使用 MySQL + Docker Compose

需要本机有 Docker Engine 和 Compose 插件，执行：

```bash
cp .env.example .env
# 请修改 .env 中的强随机 JWT_SECRET 和 MYSQL_ROOT_PASSWORD 等变量
# 默认 compose 示例仅在本地/课程演示使用
docker compose up --build -d
# Web 在 http://localhost:8000
```

`docker-compose.yml` 同时提供 `web`、`worker`、`db` 三个服务；`worker` 每2秒扫描待处理 Outbox 事件。Docker/Compose 在本次制作容器中不可用，此部署**未实际执行验证**，详见 `docs/04-测试与部署.md`。

可选的浏览器UI截图脚本需另外安装 `pip install -r requirements-ui.txt`、`playwright install chromium`，然后运行 `python scripts/capture_ui.py`。本制作环境存在浏览器URL访问限制，未生成真实浏览器截图。

## 6. 项目结构

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

## 7. 诚信声明和协作约束

项目提供可复现的**技术交付样本**；**未伪造4—5人组队、GitHub远程协作记录、个人贡献、线上部署或教师验收签字**。Git本地提交由单一作者完成，仅用于展示版本控制结构；小组应按实际情况填写报告中的成员、真实 Git 链接、个人贡献与互评。

部分需求、模型、代码与测试内容通过 AI 协助构建；最终提交前每位组员需理解代码和设计，人工完成复核并在报告中修订真实使用记录。
