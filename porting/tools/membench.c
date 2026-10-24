// Minimal memory bandwidth/latency probe for the msm8953 kernel A/B.
// Static-glibc-safe: times via the raw clock_gettime syscall, never the
// vDSO (the glibc vDSO path reads the vvar timens page, which the 6.12
// kernel maps only for time-namespace tasks and SIGBUSes otherwise), and
// never CNTVCT_EL0 (trapped, reads 0 at EL0 on this platform).
//
// Reports per-core: memcpy copy bandwidth (read+write), unrolled
// sequential-read bandwidth, and pointer-chase random-load latency.
//
//   aarch64-linux-gnu-gcc -static -O2 -o membench membench.c
//
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sched.h>
#include <unistd.h>
#include <sys/syscall.h>

#define BUF (48u * 1024 * 1024)

static double now_s(void)
{
	struct timespec ts;
	syscall(SYS_clock_gettime, CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

static int pin(int cpu)
{
	cpu_set_t set;
	CPU_ZERO(&set);
	CPU_SET(cpu, &set);
	return sched_setaffinity(0, sizeof(set), &set);
}

int main(void)
{
	unsigned char *a = aligned_alloc(64, BUF);
	unsigned char *b = aligned_alloc(64, BUF);
	unsigned int *chain;
	size_t i, n = BUF / sizeof(unsigned int);
	double t0, t1;
	int cpu;

	if (!a || !b) { perror("alloc"); return 1; }
	memset(a, 1, BUF);

	chain = (unsigned int *)a;
	for (i = 0; i < n; i++)
		chain[i] = (unsigned int)((i * 2654435761u) % n);

	for (cpu = 0; cpu <= 4; cpu += 4) {
		double bw_copy, bw_read, lat;
		volatile unsigned int sink = 0;
		size_t p = 1, steps = 16u * 1024 * 1024;

		if (pin(cpu)) { perror("affinity"); return 1; }
		sched_yield();

		memcpy(b, a, BUF);

		t0 = now_s();
		for (i = 0; i < 8; i++)
			memcpy(b, a, BUF);
		t1 = now_s();
		sink += b[0] + b[BUF / 2];  /* force the copies to happen */
		bw_copy = 2.0 * 8 * BUF / (t1 - t0) / 1e9;

		{
			unsigned long long acc = 0;
			unsigned long long *q = (unsigned long long *)a;
			size_t nq = n / 2;
			t0 = now_s();
			for (i = 0; i + 8 <= nq; i += 8)
				acc += q[i] + q[i + 1] + q[i + 2] + q[i + 3] +
				       q[i + 4] + q[i + 5] + q[i + 6] + q[i + 7];
			t1 = now_s();
			bw_read = 2.0 * nq * sizeof(unsigned long long) / (t1 - t0) / 1e9;
			if (acc == 42)
				printf(" ");
		}

		steps = 8 * n;
		t0 = now_s();
		for (i = 0; i < steps; i++)
			p = ((volatile unsigned int *)chain)[p];
		t1 = now_s();
		lat = (t1 - t0) / steps * 1e9;
		if (p == (size_t)-1)
			printf(" ");

		printf("cpu%d: copy=%.0f MB/s read=%.0f MB/s chase-lat=%.1f ns\n",
		       cpu, bw_copy * 1000, bw_read * 1000, lat);
		fflush(stdout);
	}
	(void)sink;
	free(b);
	free(a);
	return 0;
}
