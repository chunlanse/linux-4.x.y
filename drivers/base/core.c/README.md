# drivers/base/core.c — 设备驱动模型核心

`drivers/base/core.c` 实现了 Linux 设备驱动模型（driver model）的核心逻辑，
负责 `struct device` 的注册、注销、sysfs 层次管理、电源管理挂接以及与 bus/class 的联动。

## 已分析函数

| 函数 | 功能摘要 | 分析笔记 | 日期 |
|------|----------|----------|------|
| `device_add` | 将已初始化的 device 加入设备层次（sysfs、bus、class、PM、uevent、驱动探测） | [device_add.md](./device_add.md) | 2026-09-17 |

## 关键概念

- **device_register = device_initialize + device_add**：注册分两阶段，允许在加入 sysfs 前先操作设备。
- **struct device_private**：驱动核心私有数据，承载设备在父/总线/驱动/class 链表中的 klist 节点。
- **错误回滚严格反序**：`device_add` 的 goto 标签链是驱动核心资源管理的典范。
