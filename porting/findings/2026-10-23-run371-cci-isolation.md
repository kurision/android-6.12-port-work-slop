# run371-camera-cci-off: isolate CCI without rebuilding the kernel

Diagnostic image: `porting/artifacts/snapshot60/boot-run371-camera-cci-off.img`.
SHA256: `929774fdd1eea32b97db57d4b574c10e3a7f6eded4937e6b9c094540bf92a386`.

The source is the actual run370-camera boot image, verified against its
package-report SHA256. No base ramdisk was reconstructed. The existing
packager reused run370's staged kernel and init, using run370 itself as
the base, without injecting firmware, modules or policy a second time.

Verified byte-for-byte: the entire image after its 2048-byte header is
unchanged. Only command-line bytes within that header differ. Thus the
kernel, appended DTB, compressed ramdisk, init, policy, ten module/load-order
entries and seventeen firmware files are identical to run370.

Command-line changes:

- `initcall_blacklist=msm_cci_init_module`: omit only CCI driver registration;
  camera-core initialization remains enabled. KALLSYMS is enabled and the
  named initcall exists in the linked kernel.
- `initcall_debug`: emit initcall entry/return and timing messages.
- `log_buf_len=1M`: enlarge the early printk ring from its configured 128 KiB.
- Remove redundant `printk.time=1` to fit the boot header's command-line
  field; CONFIG_PRINTK_TIME is already enabled. The result is 508 bytes,
  below the 512-byte field size (including its NUL).

The early log ring helps if execution reaches the existing recorder. It
does **not** add an early persistent storage channel, re-enable the unsafe
UART, or guarantee evidence if the phone dies before the recorder starts.
No framebuffer console is enabled in this kernel, so switching console to
tty0 alone would not provide the requested panic photo channel.

The packager's firmware/modules/policy fields describe newly injected data,
not inherited data, and therefore appear empty for this image. The explicit
inheritance verification is in
`run371-camera-cci-off-verification.json`, next to the package report.

The test asks whether the camera-core/media setup can boot with CCI and its
children absent. A successful boot narrows the failure to the CCI-enabled
path or its interaction/timing, not necessarily to CCI hardware. A repeated
failure means CCI registration is not required to trigger it, assuming the
live command line confirms the blacklist. Check the skip message and live
command line before drawing either conclusion. Initcall logging itself can
alter timing, so neither result establishes a final cause from one run.

No kernel build, flash or boot was performed to prepare this image.
