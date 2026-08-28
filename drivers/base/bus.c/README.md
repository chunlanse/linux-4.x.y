# drivers/base/bus.c 函数分析

总线（bus）驱动模型核心文件，负责 bus_type 的注册/注销、驱动注册到总线、设备与总线关联等。

| 函数名 | 功能摘要 | 分析笔记 | 分析日期 |
|--------|----------|----------|----------|
| bus_add_driver | 将 device_driver 注册到所属 bus_type：创建 driver_private，sysfs 建驱动目录，挂载 bus->klist_drivers，同步/异步 autoprobe 匹配设备，关联 module，创建 uevent/bind 属性 | [bus_add_driver.md](./bus_add_driver.md) | 2026-08-29 |
