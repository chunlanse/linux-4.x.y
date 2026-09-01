# sysrq

## enable

```
#  cat /proc/sys/kernel/sysrq
0
# echo 1 > /proc/sys/kernel/sysrq
```

## trigger

```
# echo u > /proc/sysrq-trigger
```

## keys

path: drivers/tty/sysrq.c

| `sysrq_handle_crash` | #endif  CONFIG_VT | [分析笔记](./sysrq_handle_crash.md) | 2026-09-02 |
