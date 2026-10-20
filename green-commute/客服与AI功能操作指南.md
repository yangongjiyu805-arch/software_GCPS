# GreenGo 客服中心 + AI 绿色出行助手：Anaconda Prompt 操作指南

> 适用平台：Windows + Anaconda Prompt，沿用已有 `greengo` 环境和现有 SQLite 数据库。

## 一、在原项目中升级（推荐，保留原来的积分与订单）

1. 首先按 `Ctrl+C` 停止旧服务，关闭正在使用的网站标签页。
2. 下载 `GreenGo-客服与大模型-升级补丁.zip` 到 Windows「下载」文件夹。
3. 打开 **Anaconda Prompt**，依次执行：

```bat
cd /d "%USERPROFILE%\Downloads"
python -m zipfile -e "GreenGo-客服与大模型-升级补丁.zip" .
cd green-commute
conda activate greengo
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

该补丁只包含源码、测试和文档，不包含 `green_commute.db`，**原积分和订单数据不会被补丁覆盖**。如果项目不在「下载」目录，可先将升级补丁解压到项目的上一层文件夹；文件路径须与 `green-commute/app/...` 对齐。升级首次启动后数据库会自动增加客服相关表（无需删除数据库）。

## 二、不配置 AI API Key 的启动方式

```bat
cd /d "%USERPROFILE%\Downloads\green-commute"
conda activate greengo
set "JWT_SECRET=greengo-course-local-only-change-before-deployment"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`，按 **Ctrl + F5** 强制刷新缓存。登录 `resident` / `merchant` / `admin`（课程演示初始密码 `Demo@123456`）。

- 「客服中心」：居民与商户新建工单、发送补充消息；管理员查看全部工单、人工回复、更新状态。所有工单保存在当前数据库中。
- 「AI 出行助手」：没设置 API Key 时显示“未配置大模型”，发送按钮禁用，右侧固定规则 FAQ 可用。**FAQ 是普通程序规则，并非 AI 生成。**

## 三、启用真实大模型（示例：DeepSeek OpenAI 兼容 API）

需先到模型服务提供商申请**有效** API Key，可能产生调用费用。以下命令依然全部在 **Anaconda Prompt** 执行。**不要把真实 Key 发给他人或写入代码、截图、报告、Git。**

在运行服务的 Anaconda Prompt，先按 `Ctrl+C` 停止原服务，然后执行：

```bat
cd /d "%USERPROFILE%\Downloads\green-commute"
set "AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1"
set "AI_MODEL=qwen-plus"
set "AI_LOCAL_NO_KEY=0"
set "AI_API_KEY=sk-ws-H.PXMPDEL.TYCU.MEUCIQD-fPEml50HG4JRJlz4C5LtuIAemraDuJd-YHolS6ec8wIgYbazoIqyRjqJEQ_FXFxYCPiGDj-04i1xsxSNg6C14KE"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

模型名和地址以提供商最新官方文档和账户开通权限为准。切勿把 `在此粘贴...` 原样使用。**只有 Key 真实有效、模型可访问且账户有调用额度时，才能收到真正的大模型回答。**

模型提供商官方接口文档：`https://api-docs.deepseek.com/zh-cn/`。其他兼容 OpenAI Chat Completions 的服务也可以使用，只需替换环境变量 `AI_BASE_URL`、`AI_MODEL`、`AI_API_KEY`（按对应服务官方文档填写，不要在网页前端填写密钥）。

## 四、可选本地模型

如果你已经**自行运行**了一个 OpenAI 兼容本地模型服务（仅 localhost），可以在 Anaconda Prompt 配置，例如：

```bat
set "AI_BASE_URL=http://127.0.0.1:11434/v1"
set "AI_MODEL=你本地服务真实提供的模型名"
set "AI_LOCAL_NO_KEY=1"
set "AI_API_KEY="
```

该配置本身不会安装或启动模型，也不保证本地模型接口存在；必须自行准备。之后再启动 uvicorn。远程 HTTP 明文模型服务地址会被拒绝（只支持 HTTPS 或 localhost HTTP）。

## 五、实际操作与验收

1. 居民登录 → 「客服中心」 → 「新建咨询」 → 填标题、分类、正文 → 提交；退出后管理员登录，查看并回复该工单，可将状态设为「已解决」。返回居民账号，可看到管理员消息；继续回复会重新打开工单。
2. 进入「AI 出行助手」：配置有效 Key 时，输入「骑行15公里能获得多少积分？」并发送，可得到真实模型生成的回答；无 Key 则只可查看非 AI FAQ。
3. 在 Anaconda Prompt 执行 `python -m pytest -q tests`。模型适配器测试通过模拟供应商响应验证请求格式、错误处理及密钥不泄露，**不意味着已使用真实付费 Key 向第三方接口发起联网请求**。
4. API 文档在 `http://127.0.0.1:8000/docs`。客服 API 位于 `/api/support/...`，AI API 位于 `/api/assistant/...`。

## 六、安全与使用边界

- 普通用户只读取本人的客服工单；管理员作为人工客服处理全部工单。客服回复不会自动修改积分、订单和账户。
- 对话文本在服务器 SQLite 数据库保存；模型对话仅在当前浏览器页面内存中保留（关闭或刷新即清除），不写入数据库。用户主动点击发送后才把输入和最多8条历史发送给其配置的大模型服务，禁止输入敏感信息。
- 模型对外部环境、真实公交行程、账户余额和订单状态无数据库查询权限，不应据此作保证；模型输出不作为碳核算凭证。
- 教学演示版没有工单附件、短信通知、自动退款、向量知识库/RAG、人工实时在线状态和运营级 AI 计费限流。公网使用前还需实现访问限流、审计、数据保留与用户授权等措施。
