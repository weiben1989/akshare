# Mac电脑 - 一步步操作指南

> 🍎 专为Mac用户准备，每一步都有具体命令，直接复制粘贴即可！

## 📋 开始前的准备

### 1️⃣ 打开终端

**方法1（推荐）**：
- 按 `Command (⌘) + 空格`
- 输入 `terminal`
- 按回车

**方法2**：
- 打开 Finder
- 进入 `应用程序` → `实用工具` → `终端`

**终端长什么样**：
```
你的电脑名 ~ username$
```
（这个光标后面就可以输入命令了）

---

## 🔧 第一步：安装必要工具

### 检查Python版本

**复制这条命令**，粘贴到终端，按回车：
```bash
python3 --version
```

**期望结果**：
```
Python 3.8.x 或更高版本
```

**如果提示没有Python**，继续下一步安装。

---

### 安装Homebrew（Mac的软件管家）

**什么是Homebrew**？就像App Store，但是专门给开发者用的。

**复制下面整条命令**（一次性复制）：
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**注意事项**：
- 会提示输入你的Mac密码（输入时看不见，正常的）
- 需要等待5-10分钟（下载安装）
- 期间可能需要按回车确认

**安装完成后**，再运行：
```bash
brew --version
```

看到版本号就成功了！

---

### 安装Python 3

```bash
brew install python@3.11
```

等待安装完成（约3-5分钟）。

**验证安装**：
```bash
python3 --version
```

应该显示：`Python 3.11.x`

---

### 安装Git

```bash
brew install git
```

**验证**：
```bash
git --version
```

---

## 📥 第二步：下载项目代码

### 选择一个存放位置

我建议放在 `Documents` 文件夹：

```bash
# 进入文档目录
cd ~/Documents

# 创建一个专门的文件夹
mkdir quant_workspace
cd quant_workspace
```

**现在你在**：`/Users/你的用户名/Documents/quant_workspace`

---

### 下载代码

```bash
# 克隆项目
git clone https://github.com/weiben1989/akshare.git

# 进入项目
cd akshare

# 切换到我创建的分支
git checkout claude/quant-system-architecture-011CUKqu6ma7mTSufVzVD5Zy

# 进入量化系统目录
cd quant_system
```

**验证位置**：
```bash
pwd
```

应该显示类似：`/Users/xxx/Documents/quant_workspace/akshare/quant_system`

**查看文件**：
```bash
ls
```

应该看到：`README.md`, `main.py`, `analysis/` 等文件夹

---

## 🔨 第三步：安装依赖包

### 升级pip

```bash
python3 -m pip install --upgrade pip
```

---

### 安装所有依赖（一次性）

**复制下面这整条命令**（建议用国内镜像，速度快）：

```bash
pip3 install pandas numpy scipy scikit-learn sqlalchemy plotly matplotlib python-dateutil statsmodels streamlit -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**这个过程会**：
- 下载很多包（约200-300MB）
- 需要5-10分钟
- 看到进度条在走就是正常的

**如果出现权限错误**，改用：
```bash
pip3 install --user pandas numpy scipy scikit-learn sqlalchemy plotly matplotlib python-dateutil statsmodels streamlit -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 验证安装

```bash
python3 -c "import pandas; import numpy; print('✓ 安装成功！')"
```

看到 `✓ 安装成功！` 就OK了！

---

## ✅ 第四步：快速测试

```bash
# 运行测试脚本
python3 test_simple.py
```

**期望输出**：
```
🔍 A股量化系统 - 环境测试
============================================================

【测试1】检查基础库...
  ✓ Pandas版本: x.x.x
  ✓ NumPy版本: x.x.x

【测试2】检查项目模块...
  ✓ 周期分析模块导入成功

【测试3】运行基钦周期分析...
  ✓ 基钦周期运行成功
    当前阶段: 被动补库
    ...

🎉 恭喜！所有测试通过！
```

**如果看到这个，说明基础环境OK了！**

---

## 🚀 第五步：生成第一份报告

```bash
python3 main.py
```

**你会看到**：
```
╔══════════════════════════════════════════════════════════════╗
║              A股量化系统 - 每日市场分析报告                    ║
╠══════════════════════════════════════════════════════════════╣
...
```

报告会保存在 `reports/daily_report_YYYYMMDD.txt`

**查看报告**：
```bash
cat reports/daily_report_*.txt
```

---

## 🌐 第六步：启动Web可视化界面

```bash
# 启动Web界面
streamlit run web_app.py
```

**会自动弹出浏览器**，访问：`http://localhost:8501`

> ✅ **只要想确保100%真实数据**，可以在拉取更新后切到新的本地分支，并使用新的入口文件与端口：
> ```bash
> git fetch origin
> git switch -c real-data-dashboard origin/work
> streamlit run real_data_dashboard.py --server.port 8701
> ```
> - 8701 端口不会与旧版演示冲突；
> - 页面会在展示前自动校验 `data/cache` 是否包含真实数据；
> - 侧边栏提供“一键重新下载真实数据”按钮，方便你随时刷新。


**如果没自动打开**，手动在浏览器输入：`http://localhost:8501`

**你会看到**：
- 📊 市场周期仪表盘
- 📈 历史数据图表
- 💡 投资建议
- 📑 每日报告

**停止Web服务**：在终端按 `Ctrl + C`

---

## 💾 第七步：下载历史数据

```bash
# 下载历史数据（第一次运行需要时间）
python3 scripts/download_data.py
```

**这个过程会**：
- 下载近3年的历史数据
- 需要10-30分钟（取决于网络）
- 数据保存在 `data/cache/` 目录

**下载完成后**，以后再运行就会直接使用缓存，速度很快！

---

## 📅 第八步：设置每日自动运行（可选）

### 创建自动任务

```bash
# 编辑定时任务
crontab -e
```

**第一次运行会问你选择编辑器**，输入 `2` 选择 vim，按回车。

**在打开的编辑器中**：
1. 按 `i` 键（进入插入模式）
2. 复制粘贴下面这行：

```bash
0 16 * * 1-5 cd /Users/你的用户名/Documents/quant_workspace/akshare/quant_system && /usr/local/bin/python3 main.py
```

⚠️ **注意**：把 `你的用户名` 改成你的实际用户名！

**怎么知道用户名**？在终端运行：
```bash
whoami
```

3. 按 `Esc` 键（退出插入模式）
4. 输入 `:wq` 然后按回车（保存并退出）

**这个任务的含义**：
- `0 16 * * 1-5`：每周一到周五下午4点
- 会自动运行量化系统，生成报告

---

## 🎯 常用命令速查表

### 进入项目目录
```bash
cd ~/Documents/quant_workspace/akshare/quant_system
```

### 生成报告
```bash
python3 main.py
```

### 启动Web界面
```bash
streamlit run web_app.py
```

### 更新代码
```bash
git pull origin claude/quant-system-architecture-011CUKqu6ma7mTSufVzVD5Zy
```

### 查看日志
```bash
tail -f logs/quant_system_$(date +%Y%m%d).log
```

### 查看最新报告
```bash
cat reports/daily_report_$(date +%Y%m%d).txt
```

---

## 🐛 遇到问题怎么办？

### 问题1：命令找不到

**错误**：`command not found: python3`

**解决**：
```bash
# 检查Python路径
which python3

# 或使用完整路径
/usr/local/bin/python3 main.py
```

---

### 问题2：权限被拒绝

**错误**：`Permission denied`

**解决**：
```bash
# 给脚本添加执行权限
chmod +x main.py

# 或用python3明确调用
python3 main.py
```

---

### 问题3：模块找不到

**错误**：`ModuleNotFoundError: No module named 'xxx'`

**解决**：
```bash
# 重新安装缺失的模块
pip3 install xxx -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 问题4：Git相关错误

**错误**：`fatal: not a git repository`

**解决**：
```bash
# 确认在正确的目录
cd ~/Documents/quant_workspace/akshare/quant_system
pwd
```

---

### 问题5：端口被占用

**错误**：`Address already in use`（启动Web时）

**解决**：
```bash
# 查看占用端口的进程
lsof -i :8501

# 杀死进程（把PID换成上面查到的数字）
kill -9 PID

# 或换个端口启动
streamlit run web_app.py --server.port 8502
```

---

## 📖 完整工作流程

**第一次使用**：
```bash
# 1. 进入目录
cd ~/Documents/quant_workspace/akshare/quant_system

# 2. 下载历史数据（只需一次）
python3 scripts/download_data.py

# 3. 启动Web界面
streamlit run web_app.py
```

**每天使用**：
```bash
# 1. 进入目录
cd ~/Documents/quant_workspace/akshare/quant_system

# 2. 生成最新报告
python3 main.py

# 3. 查看Web界面（如果要看图表）
streamlit run web_app.py
```

**或者**，访问浏览器：`http://localhost:8501`（如果Web已经启动）

---

## 💡 小技巧

### 创建快捷命令

在 `~/.zshrc` 或 `~/.bash_profile` 中添加：

```bash
# 编辑配置文件
nano ~/.zshrc

# 添加这些行
alias quant="cd ~/Documents/quant_workspace/akshare/quant_system"
alias quant-run="cd ~/Documents/quant_workspace/akshare/quant_system && python3 main.py"
alias quant-web="cd ~/Documents/quant_workspace/akshare/quant_system && streamlit run web_app.py"

# 保存：Ctrl + O，回车，Ctrl + X
```

**然后重新加载**：
```bash
source ~/.zshrc
```

**以后只需**：
- `quant`：进入项目目录
- `quant-run`：运行报告
- `quant-web`：启动Web

---

## 🆘 常见错误怎么处理？

| 终端提示 | 解决办法 |
| --- | --- |
| `fatal: not a git repository (or any of the parent directories): .git` | 说明你还没有进入项目文件夹。运行 `cd ~/Documents/quant_workspace/akshare`（或你实际存放的位置），再继续执行后续命令。 |
| `cd: quant_system: No such file or directory` | 需要先进入仓库根目录，再执行 `cd quant_system`。连续输入：`cd ~/Documents/quant_workspace/akshare` → `cd quant_system`。 |
| `python3: command not found` | 还没有安装或配置好 Python，请返回到“安装必要工具”部分重新安装。 |
| `ModuleNotFoundError: No module named 'pandas'` | 依赖没有安装或安装在其他环境，重新执行 `pip3 install ...` 这一步即可。 |

---

## 🎉 完成！

现在你可以：
1. ✅ 每天生成市场分析报告
2. ✅ 在Web界面查看可视化图表
3. ✅ 使用历史数据（不用每次下载）
4. ✅ 设置自动运行（可选）

**有问题随时问！**

---

**下一步建议**：
1. 先运行几次，熟悉输出
2. 查看Web界面，理解各个指标
3. 阅读 `README.md` 了解原理
4. 根据需要修改 `config/settings.py` 的参数
