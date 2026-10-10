# legacy-remote-sync

**为老旧 Linux 服务器提供一条使用 Cursor 自动化编码的路径：借助旧版 VS Code 已有的 SSH 连接配置，将远程代码同步到本地，让 Cursor 阅读、修改代码，再上传回服务器。**

## 为什么需要这个 skill？

一些服务器受生产环境、实验室平台或既有软件依赖限制，无法升级 Linux。它们的 **glibc（GNU C Library）版本过老**，或其他系统依赖不满足新版工具要求，可能出现以下情况：

- 无法在服务器上安装或运行 Cursor CLI。
- Cursor IDE 的 Remote SSH 连接失败，远程 Cursor Server 无法安装或启动。
- 本地仍有一套旧版 VS Code 和兼容的 Remote SSH 扩展，可以正常连接同一台服务器。

`legacy-remote-sync` 面向这种“**旧版 VS Code 能连接，但 Cursor 的远程工具无法使用**”的场景，让你继续使用 Cursor Agent 进行代码阅读、修改和自动化编码。服务器上的数据、模型权重、GPU 和运行环境继续保留在原处，无需为了使用本 skill 在服务器上安装 Cursor CLI 或 Cursor Server。

不同工具版本对 glibc、内核和其他依赖的要求不同，本项目不指定一个通用的最低 glibc 版本，也不会升级或替换服务器的系统库。是否属于这一场景，应以实际安装或连接错误为准。

这是一套 **Cursor Agent skill + Python 命令行脚本**，支持 Agent 按需调用，也支持手工操作。同步由命令触发，不提供后台实时同步服务。

## 使用前提与工作方式

本文面向的使用前提是：**你的本地电脑已有可用的旧版 VS Code，并且配套的 Remote SSH 扩展仍能连接目标服务器、打开远程项目。** 仅安装旧版 VS Code 并不保证兼容，还需要确认扩展版本及远程组件能够在服务器上运行。

准备好以下信息：

1. 旧版 VS Code 使用的 SSH Host 别名，例如 `my-sever`。
2. 它使用的 SSH 配置文件；通常是 `~/.ssh/config`，也可能由 `remote.SSH.configFile` 指定。
3. 服务器上项目的绝对路径，例如 `/home/user/projects/demo`。
4. 可以在本地正常使用的 Cursor 和 Cursor Agent，以及下文列出的同步依赖。

实际工作流程是：

```text
旧版 VS Code + 兼容的 Remote SSH 扩展
    │ 已能访问旧 Linux 服务器，提供可复用的 SSH 配置
    ▼
Cursor Agent 调用 legacy-remote-sync
    │ 通过 SSH + rsync 下载代码，排除权重、数据和大文件
    ▼
本地代码镜像 → Cursor 阅读、搜索、修改并执行可用的本地检查
    │ 预览变更、检查远程冲突，再上传并核对
    ▼
旧 Linux 服务器上的项目代码
    └─ 使用原有依赖和数据运行；可在旧版 VS Code 远程终端中验证
```

**这里的“借助 VS Code”指复用它已经验证可用的 SSH 配置和远程工作环境。** 当前实现不包含 Cursor 点击、操控 VS Code 界面或通过 VS Code 扩展 API 编辑文件的功能；Cursor 的自动化编码发生在本地镜像中，文件传输由 SSH 和 rsync 完成。脚本运行时不要求 VS Code 窗口一直打开，也不调用 VS Code Server。

因此，旧版 VS Code 是本文场景下已验证可用的远程入口；脚本本身的连接条件是本地 OpenSSH 能登录服务器，且两端都有 rsync。远程程序运行和调试可以继续通过旧版 VS Code 的远程终端完成；需要 Agent 执行远程命令时，应在任务中明确提出。

## 功能

- 复用已有 SSH Host 配置，包括用户、端口、密钥和跳板机等连接设置。
- 默认排除模型权重、数据集、缓存和虚拟环境，单文件大小上限为 **20 MiB**。
- 将远程项目映射到本地目录，让 Cursor 在本地完成搜索、阅读和编辑。
- 基于文件内容摘要和权限模式识别新增、修改的普通文件。
- 上传前检查待上传文件是否与远程发生冲突；上传后重新下载核对。
- 默认仅预览上传，显式添加 `--apply` 才执行写入。
- 不自动删除远程文件，不传输或解引用符号链接。

## 环境要求

**本地：**

- 可正常运行的 Cursor 和 Cursor Agent（使用 skill 时需要）。
- 已能连接目标服务器的旧版 VS Code 和兼容的 Remote SSH 扩展（本文所述使用场景的前提）。
- macOS 或 Linux；Windows 用户在 WSL 中运行。
- Python **3.9+**，仅使用标准库，无需 `pip install`。
- OpenSSH 客户端（`ssh`）和 `rsync`。

**远程服务器：**

- 可以通过 SSH 登录。
- POSIX shell 和 **rsync 2.6.9+**。
- 对项目目录具有读取权限；上传时还需要相应写入权限。
- 无需安装 Python。

可以先在本地检查依赖：

```bash
python3 --version
ssh -V
rsync --version
```

Windows 下，脚本、SSH 和 rsync 需在同一个 WSL 环境中运行；原 Windows SSH 配置中的密钥路径和跳板机工具也需要能在 WSL 中使用。

## 安装为 Cursor skill

从 GitHub 下载并解压仓库，将包含 `SKILL.md` 的整个 `legacy-remote-sync` 文件夹放到以下位置之一：

- 个人安装：`~/.cursor/skills/legacy-remote-sync/`，供多个项目使用。
- 项目安装：`<项目目录>/.cursor/skills/legacy-remote-sync/`，供当前项目使用。

个人安装后的目录应为：

```text
~/.cursor/skills/legacy-remote-sync/
├── README.md
├── SKILL.md
├── references/
│   └── install.md
└── scripts/
    ├── default-excludes.txt
    └── remote_sync.py
```

不要多套一层同名目录。安装后重新打开 Cursor 项目或新建 Agent 对话，使其重新发现 skill。

### 在 Agent 中使用

首次使用时可以输入：

> 使用 legacy-remote-sync。我的旧版 VS Code 可以连接服务器，但 Cursor 因服务器系统太旧连不上。请先列出 SSH 连接名，让我选择连接，再让我选择远程项目的绝对路径。把代码同步到本地，排除模型权重和大文件。以后在本地阅读和修改代码，修改完成后上传服务器。

如果同时遇到 Cursor CLI 无法运行，可以更明确地描述环境：

> 使用 legacy-remote-sync。服务器 Linux 和 glibc 版本太旧，无法运行 Cursor CLI，也无法使用 Cursor IDE 的远程连接，但我的旧版 VS Code Remote SSH 可以正常连接。请复用它的 SSH 配置，先让我选择连接和远程项目路径，再建立本地代码镜像。请在本地完成代码修改和可执行的检查，预览后上传服务器，并报告实际上传的文件和未完成的验证。

继续阅读已有镜像：

> 使用 legacy-remote-sync，阅读当前镜像中的训练代码，解释数据处理流程。

修改并上传：

> 使用 legacy-remote-sync，修改当前镜像中的 train.py，增加早停功能，检查完成后上传服务器。

Agent 会复用镜像中保存的连接和路径。只要求阅读时不会上传；要求修改并上传时，会根据 skill 的流程预览并执行上传。

## 命令行快速开始

无需安装到 Cursor 也能使用脚本。下面假设终端位于仓库根目录，示例参数为：

- SSH Host 别名：`my-sever`。
- 远程项目：`/home/user/projects/demo`。
- 本地镜像：`~/remote-projects/my-sever/demo`。

请替换成自己的连接名和路径。`my-sever` 是脚本内置的默认别名，保留了这一拼写；脚本不会自动创建该 SSH 配置。

### 1. 选择 SSH 连接

```bash
python3 scripts/remote_sync.py hosts
```

默认从 `~/.ssh/config` 读取具体的 `Host` 别名，并解析 `Include` 文件中的别名。通配符 Host 不作为具体连接列出。

例如，已有 SSH 配置可以是：

```sshconfig
Host my-sever
    HostName server.example.com
    User your-user
    Port 22
    IdentityFile ~/.ssh/id_ed25519
```

先在终端确认该别名可以连接：

```bash
ssh my-sever
```

首次主机指纹确认或密码认证应在终端完成。脚本沿用 OpenSSH 配置，不复制私钥，也不关闭主机密钥校验。

### 2. 建立项目映射

本地镜像目录必须不存在或为空，远程路径必须是已存在的绝对路径，且不能是服务器根目录 `/`。

```bash
python3 scripts/remote_sync.py init \
  --host my-sever \
  --remote /home/user/projects/demo \
  --local ~/remote-projects/my-sever/demo
```

`init` 会连接服务器，检查项目路径和 rsync 是否可用，并创建本地同步状态；此时还没有下载项目代码。

如果需要调整排除规则，先编辑镜像内的 `.remote-sync/exclude.txt`，再执行首次下载。

### 3. 下载代码

```bash
python3 scripts/remote_sync.py pull \
  --local ~/remote-projects/my-sever/demo
```

下载成功后，用 Cursor 打开 `~/remote-projects/my-sever/demo`，在这个本地目录中阅读和修改代码。

### 4. 查看变更并上传

```bash
# 查看相对于同步基线的本地变更
python3 scripts/remote_sync.py status \
  --local ~/remote-projects/my-sever/demo

# 预览上传，并检查待上传文件的远程冲突
python3 scripts/remote_sync.py push \
  --local ~/remote-projects/my-sever/demo

# 实际上传，并重新下载核对上传内容
python3 scripts/remote_sync.py push \
  --local ~/remote-projects/my-sever/demo --apply
```

`status` 只检查本地文件与基线的差异，不连接服务器，也不检查远程变更。`push` 和 `push --apply` 都会读取远程当前内容进行检查；只有带 `--apply` 的命令才上传。

### 5. 开始下一轮修改

本地没有待同步变更时，再运行 `pull` 获取远程最新代码。若本地有修改、缺失文件或影响基线文件的排除规则变化，脚本会停止拉取，避免覆盖本地工作。

## 配置

### 自定义 SSH 配置文件

如果 VS Code 设置了 `remote.SSH.configFile`，可以显式使用同一个配置文件：

```bash
python3 scripts/remote_sync.py hosts \
  --ssh-config /path/to/ssh-config

python3 scripts/remote_sync.py init \
  --host my-sever \
  --remote /home/user/projects/demo \
  --local ~/remote-projects/my-sever/demo \
  --ssh-config /path/to/ssh-config
```

`init` 会保存该配置文件的绝对路径，后续 `pull`、`status` 和 `push` 只需传入 `--local`。初始化时未指定 `--ssh-config`，连接将使用 OpenSSH 默认配置。

### 单文件大小上限

默认上限为 **20 MiB（20 × 1024 × 1024 字节）**。初始化时可以设置其他正数，支持小数：

```bash
python3 scripts/remote_sync.py init \
  --host my-sever \
  --remote /home/user/projects/demo \
  --local ~/remote-projects/my-sever/demo \
  --max-size-mib 50
```

该上限同时用于下载和上传。初始化后，值保存在 `.remote-sync/config.json` 的 `max_size_bytes` 字段中；其他子命令没有 `--max-size-mib` 参数。

### 排除规则

默认规则来自 [scripts/default-excludes.txt](scripts/default-excludes.txt)，初始化时复制到本地镜像的 `.remote-sync/exclude.txt`。修改镜像中的文件即可为当前项目定制规则，规则采用 rsync 排除模式，并同时作用于下载、状态检查和上传。

默认排除的主要内容包括：

- 权重与模型：`*.ckpt`、`*.pt`、`*.pth`、`*.safetensors`、`*.onnx`、`weights/`、`checkpoints/` 等。
- 数据与产物：`data/`、`datasets/`、`outputs/`、`*.npy`、`*.npz`、`*.h5`、`*.hdf5` 等。
- 环境与缓存：`.venv/`、`venv/`、`node_modules/`、`__pycache__/` 和常见测试缓存。
- 日志、压缩包与视频：`logs/`、`wandb/`、`*.log`、`*.zip`、`*.tar.gz`、`*.mp4` 等。
- 项目元数据：`.git/`、`.cursor/`、`.remote-sync/` 和 `.DS_Store`。

如果源代码放在 `data/` 或 `outputs/` 内，首次下载前需调整对应规则。脚本不会自动读取项目的 `.gitignore`，小于大小上限且没有被规则排除的普通文件都会进入同步范围。

调整规则后，若原基线中的文件被新规则排除，`pull` 会暂停。保留已有工作后，可以在另一个空目录重新初始化，建立符合新规则的镜像。

### 本地同步状态

每个镜像目录包含：

```text
.remote-sync/
├── config.json      # SSH 连接、远程路径、本地路径和大小上限
├── baseline.json    # 同步基线：文件 SHA-256 摘要及权限模式
├── exclude.txt      # 当前项目的 rsync 排除规则
└── lock/            # 仅在同步操作期间存在
```

`.remote-sync/` 不会上传到服务器。映射与本地绝对路径绑定，请勿直接移动镜像或将其状态复制给其他机器、用户或服务器；更换位置时应在新的空目录重新 `init` 和 `pull`。

## 冲突处理与同步边界

上传前，脚本将待上传文件的远程当前内容与下载基线进行比较。如果远程文件已被修改、删除，或同名新增文件与本地内容不同，则停止上传；如果远程文件已经与本地待上传版本一致，则允许继续。

遇到冲突时：

1. 保留当前镜像和本地修改。
2. 使用另一个空目录，对同一远程项目重新执行 `init` 和 `pull`。
3. 比较两个镜像，将本地修改合并到具有最新基线的新镜像中。
4. 完成必要检查后，从新镜像执行 `push` 预览，再执行 `push --apply`。

同时需要了解以下行为：

- **删除不会传播。** 本地删除只会报告缺失，不会删除远程文件；重命名会上传新文件，远程旧文件仍然保留。
- **远程删除会暂停拉取。** 如果基线中的文件在远程消失，脚本保留本地文件并停止 `pull`，需要手工处理或在新空目录重新建立镜像。
- **镜像不含默认排除的 Git 历史。** 它不是完整 Git 克隆，也不是完整项目备份。
- **符号链接不参与同步。** 需要链接目标代码时，应选择目标的真实目录建立映射。
- **冲突检查不是跨机器事务。** 上传预检查与实际写入之间仍存在并发修改窗口，协作时应避免同时修改相同文件。
- **只上传变化文件不等于只扫描变化文件。** 状态检查会生成本地快照；上传预览及实际上传会下载排除规则内的远程文件进行比较，实际上传后还会重新下载核对。大项目需考虑磁盘、网络和临时空间开销。
- **同步成功不代表程序运行成功。** GPU、权重和服务器依赖仍在远程，本地检查与远程运行需分别验证。

## 常见问题

### VS Code 能连接，脚本却不能连接

确认当前终端使用的 SSH 配置、密钥路径和跳板机工具与 VS Code 一致。自定义配置可通过 `--ssh-config` 指定，并先使用 `ssh -F /path/to/ssh-config my-sever` 检查连接。

`--host` 接收 SSH Host 别名，例如 `my-sever`，不接受 `user@host` 写法。

### 是否需要在旧服务器上安装 Cursor CLI？

不需要。Cursor 和 Agent 在本地运行，脚本通过 SSH 和 rsync 读写服务器上的代码。远程仍需具备 SSH 登录能力、POSIX shell 和 rsync。

### 安装旧版 VS Code 后就一定能使用吗？

需要先确认旧版 VS Code、配套 Remote SSH 扩展及其远程组件能够连接目标服务器，再确认终端能用相同 SSH 配置登录。不同版本的兼容条件不同，本项目不提供 VS Code 安装包，也不自动降级编辑器或扩展。

### Cursor 会直接操控 VS Code 来修改远程文件吗？

当前版本通过复用 VS Code 的 SSH 配置建立本地镜像，Cursor 修改本地文件后由脚本上传。它没有 VS Code 界面自动化功能。如果需要查看远程运行结果，可以继续使用已连接的旧版 VS Code；自动执行远程任务则需在 Agent 请求中说明。

### 提示“本地有修改、缺失文件或排除规则变化”

先运行 `status` 查看差异。上传已完成的修改，或将尚未完成的工作另行保存并恢复镜像中的相关文件，再执行 `pull`。如果调整排除规则导致文件不可见，恢复规则或用新空目录建立镜像。

### 提示“有同步操作正在运行”

镜像通过 `.remote-sync/lock` 防止并行同步。如果上次进程异常退出，确认没有同步进程运行后，手工移除这个锁目录，再重试。

### 提示“上传后的文件核对失败”

此时基线不会更新，远程可能已经写入部分或全部变更。检查提示中的文件、服务器权限和并发修改情况，确认实际内容后再处理；不要将该结果视为同步完成。

### 为什么某些文件没有下载或上传？

检查 `.remote-sync/exclude.txt`、单文件大小上限，以及文件是否为符号链接。默认规则会排除整个 `data/`、`datasets/` 和 `outputs/` 等目录，其中的小文件也会被排除。

## 项目文件

- [SKILL.md](SKILL.md)：供 Cursor Agent 使用的操作流程。
- [scripts/remote_sync.py](scripts/remote_sync.py)：同步命令行实现。
- [scripts/default-excludes.txt](scripts/default-excludes.txt)：默认排除规则。
- [references/install.md](references/install.md)：补充安装与移植说明。

查看命令帮助：

```bash
python3 scripts/remote_sync.py --help
python3 scripts/remote_sync.py init --help
python3 scripts/remote_sync.py push --help
```
