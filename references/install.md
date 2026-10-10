# 安装与使用

## 移植到其他 Cursor

解压 ZIP，得到 `legacy-remote-sync` 文件夹。将整个文件夹放入以下位置之一：

- 个人 skill：`~/.cursor/skills/legacy-remote-sync/`，可供多个项目使用。
- 项目 skill：`<项目目录>/.cursor/skills/legacy-remote-sync/`，供当前项目使用。

最终应能找到 `legacy-remote-sync/SKILL.md` 和 `legacy-remote-sync/scripts/remote_sync.py`，不要多套一层同名目录。重新打开 Cursor 项目或新建 Agent 对话，使其重新发现 skill。

在 Cursor Agent 中输入：

> 使用 legacy-remote-sync。我的旧版 VS Code 可以连接服务器，但是 Cursor 因服务器系统太旧连不上。请先让我选择 SSH 连接名，默认 my-sever，然后让我选择远程项目路径。把代码同步到本地，排除 ckpt 等大文件。以后从本地读写代码，修改完成后上传服务器。

之后可以输入：

> 使用 legacy-remote-sync，阅读当前镜像中的训练代码，解释数据处理流程。

> 使用 legacy-remote-sync，修改当前镜像中的 train.py，增加早停功能，完成后上传服务器。

这是一套 Agent skill，不是 Cursor 扩展；安装后由 Agent 按说明调用脚本，不会自动建立后台实时同步服务。

## 运行环境

- macOS / Linux：本地 Python 3.9+、ssh、rsync。
- Windows：建议使用 WSL，脚本、ssh 和 rsync 在同一 WSL 环境运行。Windows VS Code 使用的 SSH 配置需要在 WSL 中能正确引用密钥和跳板机工具。
- 远程服务器：已有 SSH 登录能力、POSIX shell 和 rsync 2.6.9+。

如果 VS Code 使用自定义 SSH 配置文件，在选择连接时提供其路径。默认连接名称是 `my-sever`，实际使用者可选择自己的别名。默认值不会替其他人创建 SSH 配置。

## 手工调用

以下示例假设个人安装，远程项目为 `/home/user/project`：

```bash
python3 ~/.cursor/skills/legacy-remote-sync/scripts/remote_sync.py hosts
python3 ~/.cursor/skills/legacy-remote-sync/scripts/remote_sync.py init \
  --host my-sever --remote /home/user/project \
  --local ~/remote-projects/my-sever/project --max-size-mib 20
python3 ~/.cursor/skills/legacy-remote-sync/scripts/remote_sync.py pull \
  --local ~/remote-projects/my-sever/project
```

在 Cursor 打开 `~/remote-projects/my-sever/project`，本地修改后运行：

```bash
python3 ~/.cursor/skills/legacy-remote-sync/scripts/remote_sync.py status \
  --local ~/remote-projects/my-sever/project
python3 ~/.cursor/skills/legacy-remote-sync/scripts/remote_sync.py push \
  --local ~/remote-projects/my-sever/project
python3 ~/.cursor/skills/legacy-remote-sync/scripts/remote_sync.py push \
  --local ~/remote-projects/my-sever/project --apply
```

第一次 `push` 是预览，带 `--apply` 的命令才实际上传。`status` 只看本地变更，不检查远程是否变更。

## 排除规则与限制

初始化后编辑本地项目的 `.remote-sync/exclude.txt`，调整代码和数据的边界。默认不下载 `.git`，本地镜像不是完整 Git 克隆；如需 Git 历史，请另行设计获取方式。大小阈值保存在 `.remote-sync/config.json` 的 `max_size_bytes` 字段。

本地文件删除不会自动删除远程文件。修改排除规则可能导致基线中的文件变得不可见，脚本将停止拉取；保留修改后，可使用新的空目录重新初始化映射。镜像目录不应直接移动或复制其状态到别的机器，应重新建立映射。

上传预检查和上传之间存在并发修改窗口，协作时避免同时写同一文件。服务器 chmod 或文件系统权限差异可能使上传后核对失败，需要处理实际权限问题。

## 此压缩包的验证状态

按创建者要求，本次交付未运行脚本测试或真实服务器连接测试。压缩包不包含任何 SSH 密钥、密码、用户 SSH 配置或项目同步状态。
