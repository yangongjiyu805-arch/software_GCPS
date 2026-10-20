> **新增客服与大模型：** 已安装旧版请按 [`客服与AI功能操作指南.md`](客服与AI功能操作指南.md) 使用**升级补丁**。新项目整包名 `GreenGo-客服与AI完整项目-Anaconda版.zip`；启用真实大模型需配置 API Key，未配置时客服仍可正常使用。

# GreenGo — Windows Anaconda Prompt 操作指南

本指南所有命令都在 **Anaconda Prompt** 中执行，不需要 PowerShell、CMD、VS Code 终端、Node.js 或 Docker。`conda` 负责环境，Python 依赖通过该环境中的 `pip` 安装。请勿在 `(base)` 环境里直接安装所有项目依赖。

## 1. 首次安装

打开 Windows 开始菜单 → **Anaconda Prompt**。如果压缩包已下载到 Windows 的“下载”目录，在 Prompt 中逐行执行：

```bat
cd /d "%USERPROFILE%\Downloads"
python -m zipfile -e "GreenGo-客服与AI完整项目-Anaconda版.zip" .
cd green-commute
conda env create -f environment.yml
conda activate greengo
python --version
python -m pytest -q tests
```

**如果你是通过其他 ZIP、或已经解压了 `green-commute` 文件夹**：跳过 `python -m zipfile -e ...`，进入你已解压的 `green-commute` 文件夹即可。若下载目录是其他盘符或 OneDrive，请把 `cd /d ...` 替换为实际路径，例如：

```bat
cd /d "D:\课程项目\green-commute"
conda env create -f environment.yml
conda activate greengo
```

第一次执行 `conda env create` 需要访问 Conda 和 PyPI 源安装依赖。环境已存在时**不要重复创建**，直接 `conda activate greengo`；依赖需要同步时可以执行 `conda env update -n greengo -f environment.yml --prune`。

如果下载的文件名与示例不同，在解压命令中替换成下载后的准确文件名即可。

## 2. 启动绿色出行积分系统

在同一个 **Anaconda Prompt** 中，确保位于 `green-commute` 文件夹，且命令行左边出现 `(greengo)`：

```bat
set "JWT_SECRET=greengo-course-local-only-change-before-deployment"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

此时**不要关闭**窗口，浏览器访问：

- 系统页面：`http://127.0.0.1:8000/`
- REST API 文档：`http://127.0.0.1:8000/docs`

三组演示账号：`resident` / `merchant` / `admin`，密码均为 `Demo@123456`。本项目默认 SQLite，无需安装 MySQL。压缩包自带的 `green_commute.db` 是已录入业务数据的演示数据库；如想重置，在停止服务后执行 `del green_commute.db`，再重新启动，数据库会重建为初始状态。**重置会删除你自己新增的数据，请先备份。**

停止运行：按 **Ctrl+C**。

## 3. 自动化测试

另开或复用一个 Anaconda Prompt，进入项目目录并激活环境后执行：

```bat
conda activate greengo
cd /d "%USERPROFILE%\Downloads\green-commute"
python -m pytest -q tests
```

若你使用了其他路径，请将 `cd` 行改成自己的项目路径。测试使用临时数据库，不会修改演示数据库。

## 4. 真实接口业务流程验证

**保持第一个 Anaconda Prompt 的服务运行**；另开第二个 Anaconda Prompt，进入项目目录、激活环境并执行：

```bat
cd /d "%USERPROFILE%\Downloads\green-commute"
conda activate greengo
python scripts/demo_flow.py
```

该脚本会真实地使用 HTTP 请求完成：居民登录 → 上报30km公交 → 兑换商品 → 商户核销 → 管理员清算 → 查看积分流水，生成 `docs/evidence/demo_flow.json`。它会修改当前演示数据库，所以运行后余额及库存会变化。脚本默认监听本地8000端口。

## 5. Git 版本控制

Git 命令同样在 Anaconda Prompt 运行：

```bat
conda activate greengo
cd /d "%USERPROFILE%\Downloads\green-commute"
git --version
git status
git log --oneline -5
```

如果提示找不到 `git`，可以在 Anaconda Prompt 中安装：

```bat
conda install -c conda-forge git -y
```

**提交你本人真实作出的改动时**（首次使用请将姓名与邮箱替换为你的信息）：

```bat
git config user.name "你的姓名"
git config user.email "your-email@example.com"
git add .
git commit -m "完成个人负责的功能或测试"
```

提交前先查看 `git status` 和 `git diff`，避免把不需要的文件提交。压缩包里已有 `.git` 历史，仅属于已有的项目制作记录，不能冒充4—5位组员的真实协作记录。

## 6. 可选：重新生成 Word 实验报告

环境配置包括 `python-docx`，无需切换终端：

```bat
conda activate greengo
cd /d "%USERPROFILE%\Downloads\green-commute"
python scripts/make_report.py
```

Word 文件输出在 `green-commute` 的上级文件夹，生成后仍需用 Office/WPS 人工审阅并填写实际小组成员、AI使用与分工情况。PDF转换可在 Office/WPS 中导出。

## 7. 常见问题

- `conda 不是内部或外部命令`：请确认打开的是 **Anaconda Prompt**，不是普通 CMD。首次使用时可执行 `conda --version`。
- `EnvironmentNameNotFound`：还没有创建环境；回到项目目录执行 `conda env create -f environment.yml`。
- `CondaValueError: prefix already exists`：环境已创建，改用 `conda activate greengo`。
- `ModuleNotFoundError`：先 `conda activate greengo`，确认 `(greengo)` 出现；再运行 `python -m pip install -r requirements-dev.txt`（报告生成另需要 `python -m pip install python-docx`）。
- `Address already in use` 或 WinError 10048：8000端口已占用，结束原来的服务或将启动命令端口改为8001，并用新地址访问。
- 浏览器打不开：检查 Anaconda Prompt 是否仍显示服务运行，访问的是 `http://127.0.0.1:8000` 而不是 HTTPS。
- `No such file or directory`：请检查是否位于含有 `app`、`tests`、`environment.yml` 的 `green-commute` 项目根目录。

**边界说明**：本地 SQLite + FastAPI 可在 Conda 环境内运行。若未来需要 Docker 容器或云端部署，还需要相应系统服务；仅安装 Anaconda 并不等于已部署 Docker/MySQL。所有演示账号、积分和商品均用于教学模拟。

## 7. 登录后仍显示登录界面：旧版升级

旧版曾出现：登录成功后登录卡片没有隐藏。这是 CSS 规则覆盖 HTML `[hidden]` 属性所致。已修复且已添加自动化回归测试。

如已运行旧版项目，**无需重新安装环境**。请先在正在运行服务器的 Anaconda Prompt 中按 **Ctrl+C** 停止服务。然后下载 `GreenGo-登录界面修复补丁.zip` 至“下载”目录，在 **Anaconda Prompt** 中执行：

```bat
cd /d "%USERPROFILE%\Downloads"
python -m zipfile -e "GreenGo-登录界面修复补丁.zip" .
cd green-commute
conda activate greengo
python -m pytest -q tests
set "JWT_SECRET=greengo-course-local-only-change-before-deployment"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果项目不在“下载”目录，先把修复补丁 ZIP 移到项目文件夹的**上一级目录**，再在 Anaconda Prompt 切换到该上一级目录执行解压。补丁不会覆盖 `green_commute.db`，原有用户、积分和订单数据保留。

重新打开 `http://127.0.0.1:8000/`，按 **Ctrl+F5** 强制刷新网页，重新登录确认：登录表单隐藏、显示对应角色页面、右上角出现“退出”。
