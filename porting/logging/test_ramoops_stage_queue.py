#!/usr/bin/env python3
"""Exercise the actual stage queue against a blocked writer; no kernel build."""
from pathlib import Path
import re
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[2] / 'fs/pstore/ram.c'


def main():
    source = SOURCE.read_text()
    start = source.index('struct ramoops_stage_entry {')
    end = source.index('EXPORT_SYMBOL_GPL(ramoops_stage_write);', start)
    constants = '\n'.join(re.findall(
        r'^#define RAMOOPS_(?:STAGE_OFFSET|STAGE_SLOTS|WITNESS_LEN|SNAP_FAST_MS)\s+[^\n]+',
        source, re.M))
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
#define DEFINE_SPINLOCK(n) pthread_mutex_t n = PTHREAD_MUTEX_INITIALIZER
#define spin_lock_irqsave(l, f) do { (f) = 0; pthread_mutex_lock(l); } while (0)
#define spin_unlock_irqrestore(l, f) do { (void)(f); pthread_mutex_unlock(l); } while (0)
#define mutex_lock pthread_mutex_lock
#define mutex_unlock pthread_mutex_unlock
#define REQ_OP_WRITE 1
#define REQ_SYNC 2
#define REQ_FUA 4
static void discard_log(const char *fmt, ...) {}
#define pr_info discard_log
#define pr_warn discard_log
struct work_struct { void (*fn)(struct work_struct *); };
#define DECLARE_WORK(n, f) struct work_struct n = { f }
struct workqueue_struct {
    pthread_t thread;
    pthread_mutex_t lock;
    pthread_cond_t ready;
    struct work_struct *pending;
    bool stop;
};
static bool fail_alloc;
static atomic_bool ramoops_snap_fast;
static struct { atomic_uint wake; } ramoops_snapper;
#define smp_load_acquire(p) atomic_load_explicit((p), memory_order_acquire)
#define smp_store_release(p, v) atomic_store_explicit((p), (v), memory_order_release)
#define complete(p) atomic_fetch_add((p), 1)
static pthread_mutex_t ramoops_witness_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t io_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t io_ready = PTHREAD_COND_INITIALIZER;
static bool blocked, entered, detached;
static unsigned int writes, logged_slots[128];
static unsigned char logged_data[128];
static void *dispatch(void *arg)
{
    struct workqueue_struct *wq = arg;
    pthread_mutex_lock(&wq->lock);
    for (;;) {
        while (!wq->pending && !wq->stop)
            pthread_cond_wait(&wq->ready, &wq->lock);
        if (!wq->pending && wq->stop)
            break;
        struct work_struct *work = wq->pending;
        wq->pending = NULL;
        pthread_mutex_unlock(&wq->lock);
        work->fn(work);
        pthread_mutex_lock(&wq->lock);
    }
    pthread_mutex_unlock(&wq->lock);
    return NULL;
}
static struct workqueue_struct *alloc_ordered_workqueue(const char *name, int flags)
{
    if (fail_alloc)
        return NULL;
    struct workqueue_struct *wq = calloc(1, sizeof(*wq));
    assert(wq);
    pthread_mutex_init(&wq->lock, NULL);
    pthread_cond_init(&wq->ready, NULL);
    assert(!pthread_create(&wq->thread, NULL, dispatch, wq));
    return wq;
}
static bool queue_work(struct workqueue_struct *wq, struct work_struct *work)
{
    pthread_mutex_lock(&wq->lock);
    bool fresh = !wq->pending;
    wq->pending = work;
    pthread_cond_signal(&wq->ready);
    pthread_mutex_unlock(&wq->lock);
    return fresh;
}
static void destroy_workqueue(struct workqueue_struct *wq)
{
    pthread_mutex_lock(&io_lock);
    detached = true;
    pthread_cond_broadcast(&io_ready);
    pthread_mutex_unlock(&io_lock);
    pthread_mutex_lock(&wq->lock);
    wq->stop = true;
    pthread_cond_signal(&wq->ready);
    pthread_mutex_unlock(&wq->lock);
    assert(!pthread_join(wq->thread, NULL));
    pthread_mutex_destroy(&wq->lock);
    pthread_cond_destroy(&wq->ready);
    free(wq);
}
static int ramoops_witness_write_at(uint64_t offset, int flags,
                                   const void *data, size_t len)
{
    assert(flags == (REQ_OP_WRITE | REQ_SYNC | REQ_FUA));
    assert(len == 1 || len == RAMOOPS_WITNESS_LEN);
    pthread_mutex_lock(&io_lock);
    entered = true;
    pthread_cond_broadcast(&io_ready);
    while (blocked)
        pthread_cond_wait(&io_ready, &io_lock);
    assert(writes < 128);
    logged_slots[writes] = (offset - RAMOOPS_STAGE_OFFSET) / RAMOOPS_WITNESS_LEN;
    logged_data[writes++] = *(const unsigned char *)data;
    pthread_mutex_unlock(&io_lock);
    return -EIO; /* Failed storage must not stop later records draining. */
}
'''
    check = r'''
static void *stop_queue(void *unused)
{
    ramoops_stage_stop();
    return NULL;
}
int main(void)
{
    unsigned char data[RAMOOPS_WITNESS_LEN] = { 77 };
    assert(!atomic_load(&ramoops_snap_fast) && atomic_load(&ramoops_snapper.wake) == 0);
    assert(ramoops_stage_write(0, data, 1) == -ENODEV);
    /* Stage activity wakes the snapshotter even before its queue is ready. */
    assert(atomic_load(&ramoops_snap_fast) && atomic_load(&ramoops_snapper.wake) == 1);
    fail_alloc = true;
    ramoops_stage_start();
    assert(ramoops_stage_write(0, data, 1) == -ENODEV);
    fail_alloc = false;
    ramoops_stage_start();
    assert(ramoops_stage_write(RAMOOPS_STAGE_SLOTS, data, 1) == -EINVAL);
    assert(ramoops_stage_write(0, data, sizeof(data) + 1) == -EINVAL);

    blocked = true;
    assert(!ramoops_stage_write(31, data, sizeof(data)));
    assert(atomic_load(&ramoops_snap_fast) && atomic_load(&ramoops_snapper.wake) == 1);
    pthread_mutex_lock(&io_lock);
    while (!entered)
        pthread_cond_wait(&io_ready, &io_lock);
    pthread_mutex_unlock(&io_lock);
    /* The worker holds the witness mutex and is stuck in storage here. */
    for (unsigned int i = 0; i < RAMOOPS_STAGE_SLOTS; i++) {
        data[0] = i;
        assert(!ramoops_stage_write(i, data, 1));
        data[0] = 255; /* Queued entries must own their copy. */
    }
    assert(ramoops_stage_write(0, data, 1) == -ENOSPC);

    pthread_t stopper;
    assert(!pthread_create(&stopper, NULL, stop_queue, NULL));
    pthread_mutex_lock(&io_lock);
    while (!detached)
        pthread_cond_wait(&io_ready, &io_lock);
    pthread_mutex_unlock(&io_lock);
    assert(ramoops_stage_write(0, data, 1) == -ENODEV);
    pthread_mutex_lock(&io_lock);
    blocked = false;
    pthread_cond_broadcast(&io_ready);
    pthread_mutex_unlock(&io_lock);
    assert(!pthread_join(stopper, NULL));
    assert(writes == RAMOOPS_STAGE_SLOTS + 1);
    assert(logged_slots[0] == 31 && logged_data[0] == 77);
    for (unsigned int i = 0; i < RAMOOPS_STAGE_SLOTS; i++) {
        assert(logged_slots[i + 1] == i);
        assert(logged_data[i + 1] == i);
    }
    /* Restart and drain again, including wrapped head/tail indices. */
    ramoops_stage_start();
    for (unsigned int i = 0; i < RAMOOPS_STAGE_SLOTS; i++)
        assert(!ramoops_stage_write(i, data, 1));
    ramoops_stage_stop();
    assert(writes == 2 * RAMOOPS_STAGE_SLOTS + 1);
    assert(atomic_load(&ramoops_snapper.wake) == 1);
    ramoops_stage_stop();
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix='ack-stage-test-', dir='/tmp/opencode') as tmp:
        root = Path(tmp)
        unit = root / 'stage.c'
        unit.write_text(constants + '\n' + harness + source[start:end] + check)
        subprocess.run(['cc', '-std=gnu11', '-pthread', '-Wall', '-Wextra',
                        '-Werror', '-Wno-unused-parameter', str(unit),
                        '-o', str(root / 'stage')], check=True, timeout=20)
        subprocess.run([str(root / 'stage')], check=True, timeout=10)
    print('stage queue: blocked storage, bounds, copies, FIFO, errors, teardown passed')


if __name__ == '__main__':
    main()
