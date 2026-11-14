do_exit
========================================

进程/线程终止的统一收尾函数。所有 `exit(2)`、`exit_group(2)`、致命信号、内核线程返回等终止路径，最终都汇聚到 `kernel/exit.c` 的 `do_exit()`；它按“信号 → 地址空间 → IPC → 文件 → 命名空间 → 架构资源 → 通知父进程”的顺序拆解资源，最后调用 `do_task_dead()` 置 `TASK_DEAD` 并主动让出 CPU，永不返回。

Analysis
----------------------------------------

- 日期：2026-11-15
- 子系统：kernel
- 源文件：kernel/exit.c:728-887（Linux v4.9）
- 类型：function（`EXPORT_SYMBOL_GPL`）

完整解读（功能作用、关键数据结构、核心逻辑流程图、调用关系、易错点）：

[每日归档：kernel_do_exit.md](../../daily/2026/11/2026-11-15/kernel_do_exit.md)

Key Points
----------------------------------------

1. `group_dead = atomic_dec_and_test(&signal->live)`：只有线程组最后一个线程退出，才做 `real_timer`、记账、控制终端等进程级清理。
2. `exit_mm()`：先 `atomic_inc(&mm->mm_count)` 再清 `tsk->mm`，转入 lazy TLB；若正在 coredump，通过 `core_state->dumper` 握手睡眠等待。
3. `exit_notify()`：`forget_original_parent()` 重新挂接子进程，`do_notify_parent()` 向父进程发 `SIGCHLD`，再根据 `autoreap` 置 `EXIT_ZOMBIE` / `EXIT_DEAD`。
4. `PF_EXITING` 已置位说明清理路径递归崩溃：置 `PF_EXITPIDONE` 后永久 `schedule()`，等待重启，不做资源回收。
5. `do_task_dead()` 之后 `task_struct` 会在 `finish_task_switch()` 中被 `put_task_struct()` 释放，不能再访问 `current`。

Source
----------------------------------------

```c
void __noreturn do_exit(long code)
{
	struct task_struct *tsk = current;
	int group_dead;
	TASKS_RCU(int tasks_rcu_i);

	profile_task_exit(tsk);
	kcov_task_exit(tsk);
	WARN_ON(blk_needs_flush_plug(tsk));

	if (unlikely(in_interrupt()))
		panic("Aiee, killing interrupt handler!");
	if (unlikely(!tsk->pid))
		panic("Attempted to kill the idle task!");

	set_fs(USER_DS);
	ptrace_event(PTRACE_EVENT_EXIT, code);
	validate_creds_for_do_exit(tsk);

	if (unlikely(tsk->flags & PF_EXITING)) {
		pr_alert("Fixing recursive fault but reboot is needed!\n");
		tsk->flags |= PF_EXITPIDONE;
		set_current_state(TASK_UNINTERRUPTIBLE);
		schedule();
	}

	exit_signals(tsk);	/* sets PF_EXITING */
	smp_mb();
	raw_spin_unlock_wait(&tsk->pi_lock);

	if (unlikely(in_atomic()))
		preempt_count_set(PREEMPT_ENABLED);

	if (tsk->mm)
		sync_mm_rss(tsk->mm);
	acct_update_integrals(tsk);
	group_dead = atomic_dec_and_test(&tsk->signal->live);
	if (group_dead) {
		hrtimer_cancel(&tsk->signal->real_timer);
		exit_itimers(tsk->signal);
		if (tsk->mm)
			setmax_mm_hiwater_rss(&tsk->signal->maxrss, tsk->mm);
	}
	acct_collect(code, group_dead);
	if (group_dead)
		tty_audit_exit();
	audit_free(tsk);

	tsk->exit_code = code;
	taskstats_exit(tsk, group_dead);

	exit_mm(tsk);

	if (group_dead)
		acct_process();
	trace_sched_process_exit(tsk);

	exit_sem(tsk);
	exit_shm(tsk);
	exit_files(tsk);
	exit_fs(tsk);
	if (group_dead)
		disassociate_ctty(1);
	exit_task_namespaces(tsk);
	exit_task_work(tsk);
	exit_thread(tsk);

	perf_event_exit_task(tsk);
	sched_autogroup_exit_task(tsk);
	cgroup_exit(tsk);
	flush_ptrace_hw_breakpoint(tsk);

	TASKS_RCU(preempt_disable());
	TASKS_RCU(tasks_rcu_i = __srcu_read_lock(&tasks_rcu_exit_srcu));
	TASKS_RCU(preempt_enable());
	exit_notify(tsk, group_dead);
	proc_exit_connector(tsk);
	mpol_put_task_policy(tsk);
#ifdef CONFIG_FUTEX
	if (unlikely(current->pi_state_cache))
		kfree(current->pi_state_cache);
#endif
	debug_check_no_locks_held();
	tsk->flags |= PF_EXITPIDONE;

	if (tsk->io_context)
		exit_io_context(tsk);
	if (tsk->splice_pipe)
		free_pipe_info(tsk->splice_pipe);
	if (tsk->task_frag.page)
		put_page(tsk->task_frag.page);

	validate_creds_for_do_exit(tsk);
	check_stack_usage();
	preempt_disable();
	if (tsk->nr_dirtied)
		__this_cpu_add(dirty_throttle_leaks, tsk->nr_dirtied);
	exit_rcu();
	TASKS_RCU(__srcu_read_unlock(&tasks_rcu_exit_srcu, tasks_rcu_i));

	do_task_dead();
}
EXPORT_SYMBOL_GPL(do_exit);
```
