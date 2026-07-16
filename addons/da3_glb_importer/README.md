# DA3 Colored GLB Importer

Blender 5.2 插件，用于一键导入 DA3 生成的 GLB 彩色点云。

插件会强制以 Blender 原生 `PointCloud` 导入 glTF `POINTS` primitive，随后从 GLB 的 `COLOR_0` 恢复逐点颜色，执行 sRGB 到 Linear 的正确映射，并创建不依赖灯光的 Emission 显示材质。

## 安装

1. 使用仓库 `dist/da3_glb_importer-0.1.0.zip`，或者自行将 `da3_glb_importer` 文件夹压缩为 ZIP。
2. 在 Blender 中打开 `Edit > Preferences > Add-ons`。
3. 选择 `Install from Disk` 并安装 ZIP。
4. 启用 `DA3 Colored GLB Importer`。

## 使用

选择 `File > Import > DA3 Colored Point Cloud (.glb)`，然后选择 DA3 GLB 文件。

插件自动完成：

- 启用 `Import Points as Point Cloud`
- 读取 normalized unsigned-byte `COLOR_0`（`VEC3` 或 `VEC4`）
- 严格核对 GLB 颜色数量与 Blender 点数
- 将图像来源的 sRGB 颜色转换为 Linear
- 创建点域 `FLOAT_COLOR` 属性 `color`
- 使用 Geometry Nodes 设置 Emission 材质
- 切换到 `Standard`、黑色 World 和无场景灯光的 Rendered 视图

如果点数无法唯一匹配或 GLB 颜色格式不符合预期，插件会停止并撤销本次导入对象，不会猜测颜色对应关系。

## 关于 Import Points as Point Cloud

这个选项决定 glTF `mode: 0` 的 `POINTS` primitive 是否导入为 Blender 原生 `PointCloud`。本插件依赖原生点云的数据结构和 Geometry Nodes 显示流程，因此始终开启该选项，不需要用户手动设置。
