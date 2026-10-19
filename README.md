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

## Blender 插件

`addons/da3_glb_importer` 提供 `File > Import > DA3 Colored Point Cloud (.glb)`，用于一键导入 DA3 GLB、恢复点云 `COLOR_0`、完成 sRGB 到 Linear 映射，并建立不依赖灯光的 Emission 显示。点半径覆盖默认关闭，需要时可在导入选项或 Geometry Nodes 修改器中开启。可直接安装 [`dist/da3_glb_importer-0.2.0.zip`](dist/da3_glb_importer-0.2.0.zip)。

安装方法见 [`addons/da3_glb_importer/README.md`](addons/da3_glb_importer/README.md)。

### 🍊 Visibility Scanner - Object Classification

检测产品或 CAD 装配体的外部可见对象与内部候选对象，不删除模型。默认使用 GPU ID 扫描，再以 BVH 射线复核未发现的对象。结果作为额外链接放入 `VIS_SCAN_RESULTS`，保留原集合归属、层级和几何。

安装 [`dist/orange_visibility_scanner-1.0.2.zip`](dist/orange_visibility_scanner-1.0.2.zip) 后，在 3D 视图的 `N > 🍊 Visibility` 中使用。操作说明见 [`addons/orange_visibility_scanner/README.md`](addons/orange_visibility_scanner/README.md)，Agent 复用说明见[经验卡](references/object-visibility-scanner.md)。

## 当前内容

- GLB/GLTF 点云 `COLOR_0` 丢失后的诊断与恢复
- 不依赖灯光的点云属性色与 Emission 显示流程
- DA3 彩色 GLB 一键导入插件
- 🍊 对象可见性扫描与内部候选分类插件
- 可复用的 `restore_glb_point_colors.py` 恢复脚本

核心使用说明见 [`SKILL.md`](SKILL.md)，详细经验卡位于 [`references/`](references/)。
