---
name: legacy-remote-sync
description: 当老旧 Linux 服务器无法运行 Cursor Remote SSH、但旧版 VS Code 能连接时，复用 VS Code 的 SSH Host 配置，把远程代码排除权重和大文件后同步到本地，在 Cursor 本地阅读和修改，再将修改上传到服务器。
---

# 老旧服务器的本地代码同步

通过 SSH 和 rsync 建立本地代码镜像，让 Cursor 在本地工作。服务器继续保留数据、权重和运行环境，无需启动 Cursor Server。

## 首次使用：依次选择连接和项目

1. 先让用户选择旧版 VS Code 使用的 SSH 连接名，默认候选为 **`my-sever`**（保留此拼写）。执行本 skill 的 `scripts/remote_sync.py hosts` 列出 SSH 配置中的具体 Host 别名，再向用户展示候选。不要在未选择时连接所有服务器。
2. 如果 VS Code 设置了 `remote.SSH.configFile`，使用那个配置文件，所有相关命令都传入 `--ssh-config`。默认采用 `~/.ssh/config`。沿用其中的 User、Port、IdentityFile、ProxyJump 等配置，不复制私钥，不修改 SSH 配置或关闭主机密钥校验。
3. 连接名确定后，让用户选择**服务器项目的绝对路径**，例如 `/home/user/projects/demo`；不要猜测路径。需要列举候选时，仅通过 SSH 只读查看用户指定的父目录，并对 shell 路径正确引用。
4. 选择本地镜像目录。建议放在 `~/remote-projects/<连接名>/<项目名>`；用户未指定时可采用该建议并告知。首次初始化必须使用不存在或为空的目录。让 Cursor 打开这个镜像目录，而不是远程窗口。
5. 本地需要 Python 3.9+、OpenSSH、rsync；服务器需要 POSIX shell 和 rsync 2.6.9+，不需要 Python。Windows 在 WSL 中运行脚本，SSH 配置及密钥也必须能在 WSL 中使用。依赖缺失时说明缺失项，不自动升级服务器或卸载 IDE。

## 建立映射并下载

所有脚本路径都相对于本 `SKILL.md` 所在目录；执行前确定脚本的实际绝对路径。以下命令中的路径是示例，替换成用户选择的真实值。

```bash
python3 /path/to/legacy-remote-sync/scripts/remote_sync.py hosts
python3 /path/to/legacy-remote-sync/scripts/remote_sync.py init \
  --host my-sever \
  --remote /home/user/projects/demo \
  --local ~/remote-projects/my-sever/demo
python3 /path/to/legacy-remote-sync/scripts/remote_sync.py pull \
  --local ~/remote-projects/my-sever/demo
```

`init` 只建立映射，`pull` 才下载。需要自定义 SSH 配置时，给 `hosts` 和 `init` 加 `--ssh-config /path/to/ssh-config`，后续命令自动使用保存的配置。

同步状态保存在本地镜像的 `.remote-sync/`：连接、远程路径、本地路径、文件摘要基线和排除规则。该目录不会上传；不将此状态复制给其他服务器或其他用户。

## 排除大文件

默认单文件上限是 **20 MiB**，可在 `init` 时用 `--max-size-mib` 调整。默认排除规则见 [scripts/default-excludes.txt](scripts/default-excludes.txt)：包括 ckpt、pt、pth、safetensors、模型权重目录、数据集目录、缓存、虚拟环境、日志和常见二进制文件。

按项目实际结构调整镜像的 `.remote-sync/exclude.txt`；该规则同时用于下载和上传。如果源代码位于 `data/`、`outputs/` 等默认排除目录，首次下载前移除对应规则；必须阅读的小配置或测试样本也可以按需放行。不要为了少量代码放开整个权重目录。默认不传输或解引用符号链接；需要链接目标代码时，应单独选择其真实目录。

## 日常阅读、修改与上传

- 用户只要求读代码或解释代码时，从本地镜像读取，不上传没有发生的变更。
- 继续已有项目时读取 `.remote-sync/config.json`，复用已选择的连接和路径；只有用户切换项目或映射不存在时才重新选择。
- 开始新一轮修改前，本地无未同步变更时执行 `pull` 获取远程最新代码；有本地修改时先保留修改，不用拉取覆盖它。
- 所有搜索、阅读和编辑在本地完成。完成修改后执行必要的项目检查，检查范围按用户任务决定；本地缺少 GPU、权重或依赖时如实说明，远程运行仅在用户要求或已授权时进行。
- 用户已经要求“修改后上传”时，完成修改后自动预览并上传，不重复请求相同授权；用户只要求本地修改时保留本地结果。

```bash
python3 /path/to/legacy-remote-sync/scripts/remote_sync.py status \
  --local ~/remote-projects/my-sever/demo
python3 /path/to/legacy-remote-sync/scripts/remote_sync.py push \
  --local ~/remote-projects/my-sever/demo
python3 /path/to/legacy-remote-sync/scripts/remote_sync.py push \
  --local ~/remote-projects/my-sever/demo --apply
```

`push` 默认只预览，`push --apply` 实际上传。只上传相对于基线新增或改变的普通文件，上传后重新下载核对内容。脚本默认不删除服务器文件；本地删除或重命名会提示，重命名的旧文件仍留在远程。用户任务需要删除旧文件时，先明确列出这些文件，再按已有授权单独处理，不能改成全目录 `--delete`。

## 冲突和失败

上传前比较待上传文件的远程内容和下载基线。服务器文件已经被别人修改或删除时停止上传，不强制覆盖。保存本地修改，通过另一个临时空镜像拉取当前远程版本，在本地比较并合并；完成合并后从这个具有最新基线的镜像上传。失败时保留原镜像，不宣称同步完成。

SSH 验证需要密码或首次确认主机指纹时，让用户在终端完成；不要求在聊天中提供密码。SSH 无法连接时停在连接诊断，明确指出旧版 VS Code 能连接并不保证当前终端的 SSH 配置相同。

上传核对失败、权限不足或 rsync 不可用时说明实际错误，不循环重试，不自动安装服务器依赖。同步不是跨机器事务，上传期间避免同时修改相同文件；脚本能拦截检查时已存在的冲突，但无法消除远程并发修改的时间窗口。

交付时报告本地目录、远程连接和项目路径、实际上传文件、被排除文件的范围以及未解决的错误。不要把“本地检查通过”写成“服务器运行通过”。

移植和手工使用说明见 [references/install.md](references/install.md)。
