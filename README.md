# Blender Playbook

个人 Blender 经验技能库，用于沉淀并复用经过真实场景验证的工作流、技巧、诊断方法和自动化脚本。

## 安装

在 PowerShell 中运行：

```powershell
git clone https://github.com/Purextreme/blender-playbook.git "$env:USERPROFILE\.codex\skills\blender-playbook"
```

安装后重启 Codex。使用时可以明确指定 `$blender-playbook`，也可以在 Blender 相关任务中由 Codex 自动加载。

## 更新

```powershell
git -C "$env:USERPROFILE\.codex\skills\blender-playbook" pull --ff-only
```

## 当前内容

- GLB/GLTF 点云 `COLOR_0` 丢失后的诊断与恢复
- 不依赖灯光的点云属性色与 Emission 显示流程
- 可复用的 `restore_glb_point_colors.py` 恢复脚本

核心使用说明见 [`SKILL.md`](SKILL.md)，详细经验卡位于 [`references/`](references/)。
