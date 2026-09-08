# vfs_fallocate

> 归档日期：2026-09-09 | 子系统：fs | 源文件：fs/open.c:225-315 | 内核版本：Linux 4.1.6
> 完整分析：[../../daily/2026/09/2026-09-09/fs_vfs_fallocate.md](../../daily/2026/09/2026-09-09/fs_vfs_fallocate.md)

## 功能作用

`vfs_fallocate` 是 VFS 层处理 **fallocate（文件空间预分配 / 打洞 / 清零 / 折叠 / 插入范围）** 操作的统一入口。它集中完成参数校验、标志互斥检查、权限与 inode 属性校验，然后通过 `file->f_op->fallocate` 回调把具体实现下沉到具体文件系统（如 ext4、XFS）。

## 核心逻辑

1. 参数校验：`offset >= 0`、`len > 0`。
2. 模式标志校验：不支持的位、`PUNCH_HOLE` 与 `ZERO_RANGE` 互斥、`PUNCH_HOLE` 必须带 `KEEP_SIZE`、`COLLAPSE_RANGE`/`INSERT_RANGE` 必须独占。
3. 权限与属性校验：`FMODE_WRITE`、append-only、immutable、swapfile、FIFO、非普通/目录文件。
4. LSM 二次写权限校验 `security_file_permission(file, MAY_WRITE)`。
5. 范围越界检查：`offset + len` 不超过 `sb->s_maxbytes` 且不溢出回绕。
6. `sb_start_write` → `f_op->fallocate` → 成功则 `fsnotify_modify` → `sb_end_write`。

## 调用者

- `fallocate(2)` 系统调用（fs/open.c）
- `FIBMAP` ioctl（fs/ioctl.c，32 位兼容走 compat_ioctl）
- `madvise(MADV_REMOVE)`（mm/madvise.c）
- NFSv4 服务端 `nfsd4_vfs_fallocate`（fs/nfsd/vfs.c）
- Android ashmem 驱动（drivers/staging/android/ashmem.c）

## 关键数据结构

- `struct file`（`f_mode`、`f_op`、`f_inode`）
- `struct inode`（`i_flags`、`i_mode`、`i_sb`）
- `struct super_block`（`s_maxbytes`）
- `FALLOC_FL_*` 标志（include/uapi/linux/falloc.h）
