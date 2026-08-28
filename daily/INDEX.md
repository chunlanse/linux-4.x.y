# Linux 内核源码每日学习索引

> 最后更新：2026-08-29 | 累计分析：**866** 个核心函数/结构

本文件按**日期倒序**维护每日学习条目。同时可参考：
- [按子系统索引](./by-subsystem.md)
- [进度统计 JSON](./progress-stats.json)

---

## 按日期倒序

### 2026-08-29（drivers/base）

- **目标**：`bus_add_driver`（function）
- **源码**：`drivers/base/bus.c:634-704`（Linux 4.19 LTS）
- **摘要**：将 device_driver 注册到所属 bus_type：创建 driver_private 私有对象、sysfs 建驱动目录、挂载 bus->p->klist_drivers、同步/异步 autoprobe 匹配总线已有设备、关联 module、创建 uevent 和 bind/unbind 属性文件
- **完整笔记**：[drivers/base/bus_add_driver](./2026/08/2026-08-29/drivers_bus_add_driver.md)
- **子系统就地路径**：`/workspace/drivers/base/bus.c/bus_add_driver.md`
