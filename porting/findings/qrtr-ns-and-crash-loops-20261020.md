# QRTR name service and the vendor crash loops — 2026-10-20

## What the phone was doing

The running image was `6.12.93-4k-g15c6948f88d9` (the pre-fix image;
HEAD has the four new commits).  `sys.init.updatable_crashing` was `1`,
and `dmesg` showed the health-check action still firing:

```
[  793.625250] init: Service 'exec 497 (/system/bin/flags_health_check UPDATABLE_CRASHING)' ...
[  794.485837] init: processing action (sys.init.updatable_crashing=1) from (/system/etc/init/flags_health_check.rc:10)
[  794.460495] init: Service 'vendor.qrtr-ns' (pid 9583) exited with status 1
[  935.282040] init: process with updatable components 'vendor.per_mgr' exited 4 times in 4 minutes
[  936.472557] init: process with updatable components 'vendor.dataqti' exited 4 times in 4 minutes
```

The service states were:

```
init.svc.vendor.qrtr-ns=restarting
init.svc.vendor.per_mgr=restarting
init.svc.vendor.per_proxy=restarting
init.svc.qcamerasvr=restarting
init.svc.vendor.dataqti=restarting/running
```

The health-check removal (`8f238506a`) stops the `flags_health_check`
exec storm.  It does not stop the services; each crash still restarts on
the init `restart_period`, and each one keeps the updatable-component
property set.

## `vendor.qrtr-ns`: a capability mismatch, and a missing policy allow

The service definition grants only `NET_BIND_SERVICE`:

```text
/vendor/etc/init/hw/init.qcom.rc:405 service vendor.qrtr-ns /vendor/bin/qrtr-ns -f
/vendor/etc/init/hw/init.qcom.rc:406     class core
/vendor/etc/init/hw/init.qcom.rc:407     user vendor_qrtr
/vendor/etc/init/hw/init.qcom.rc:408     group vendor_qrtr
/vendor/etc/init/hw/init.qcom.rc:409     capabilities NET_BIND_SERVICE
```

The 6.12 QRTR port allocator requires `CAP_NET_ADMIN` for a fixed port
below `QRTR_MIN_EPH_SOCKET` (0x4000):

```text
net/qrtr/af_qrtr.c:21   #define QRTR_MIN_EPH_SOCKET 0x4000
net/qrtr/af_qrtr.c:736  } else if (*port < QRTR_MIN_EPH_SOCKET && !capable(CAP_NET_ADMIN)) {
net/qrtr/af_qrtr.c:737          rc = -EACCES;
```

The kernel QRTR name service binds the control port itself:

```text
net/qrtr/ns.c:771  sq.sq_port = QRTR_PORT_CTRL;
net/qrtr/ns.c:774  ret = kernel_bind(qrtr_ns.sock, (struct sockaddr *)&sq, sizeof(sq));
net/qrtr/ns.c:782  qrtr_ns.bcast_sq.sq_port = QRTR_PORT_CTRL;
```

so the userspace daemon binds the separate QRTR name-service port and
needs `CAP_NET_ADMIN`; it does not conflict with the in-kernel control
port.  Running the binary as root (with the capability) stayed alive;
running it in the service's SELinux domain reproduced the failure:

```text
$ runcon u:r:qrtr:s0 /vendor/bin/qrtr-ns -f
qrtr-ns: bind control socket: Permission denied
exit=1

avc: denied { net_admin } for comm="qrtr-ns" capability=12
     scontext=u:r:qrtr:s0 tcontext=u:r:qrtr:s0
     tclass=capability permissive=0
```

Both halves are required:

* the init override adds `NET_ADMIN` to the service's capability set;
* `porting/policy/port-genfs-kgsl.cil` adds
  `(allow qrtr self (capability (net_admin)))`.

## `vendor.per_mgr` and `vendor.per_proxy`: camera peripheral manager

```text
/vendor/etc/init/hw/init.target.rc:93  service vendor.per_mgr /vendor/bin/pm-service
/vendor/etc/init/hw/init.target.rc:101 service vendor.per_proxy /vendor/bin/pm-proxy
/vendor/etc/init/hw/init.target.rc:106     disabled
/vendor/etc/init/hw/init.target.rc:109 on property:init.svc.vendor.per_mgr=running
/vendor/etc/init/hw/init.target.rc:110     start vendor.per_proxy
```

`pm-service` exits 255; it still exits 255 when run as root with
`qrtr-ns` running, so this is not the QRTR capability and not a missing
socket on this boot.  It never reaches the peripheral-manager QMI
service.  `pm-proxy` is guarded by `per_mgr=running`, so it only starts
and exits 1 when per_mgr briefly comes up.  This is the camera
peripheral-manager stack, which is not part of this bring-up pass.

## `qcamerasvr`: camera daemon

```text
/vendor/etc/init/hw/init.target.rc:86 service qcamerasvr /system/vendor/bin/mm-qcamera-daemon
/vendor/etc/init/hw/init.target.rc:87     class main
```

It exits 0 and init restarts it.  The repeated denial is real:

```text
avc: denied { write } for comm="mm-qcamera-daem" name="property_service"
     scontext=u:r:mm-qcamerad:s0 tcontext=u:object_r:property_socket:s0
     tclass=sock_file permissive=0
```

The camera stack also depends on `per_mgr`, so the denial is not the
only blocker.  Camera is out of scope for this pass; add the
`property_socket` allow only when the camera stack is brought up.

## `vendor.dataqti`: waits for the rmnet/MHI node

```text
/vendor/etc/init/dataqti.rc:14 service vendor.dataqti /system/vendor/bin/qti
/vendor/etc/init/dataqti.rc:15     class main
/vendor/etc/init/dataqti.rc:16     user radio
/vendor/etc/init/dataqti.rc:19     disabled
```

The service is disabled, but a vendor HAL starts it (`ctl.start`) at
boot.  `qti` retries ten times and exits:

```text
E/QTI_SDM_INFO: [qti_rmnet_peripheral.c:768] qti_file_open(): Could not open device file. Errno 2
E/QTI_SDM_INFO: [qti_rmnet_peripheral.c:842] qti_rmnet_ph_init(): Failed to open USB peripheral device file after 10 attempts.
E/QTI_SDM_INFO: [qti_main.c:742] main(): Failed to initialize QTI peripheral interface
```

The binary's paths are `/dev/rmnet_ctrl0`, `/dev/smdcntl8` and the MHI
pipes; none exist on this boot.  This is the USB/DPM data path, not the
main rmnet data path, and it becomes valid only when the modem data
path is up.  Keep it stopped until that bring-up.

## The overlay

`scripts/initramfs-diag/init.c` appends these definitions to the
filtered `flags_health_check.rc` (parsed after the vendor init files, so
`override` replaces the vendor services before `class_start`):

* `vendor.qrtr-ns` with `NET_BIND_SERVICE NET_ADMIN`, `override`;
* `vendor.per_mgr` and `qcamerasvr` with `disabled`, `override`;
* `vendor.dataqti` stopped on `init.svc.vendor.dataqti=running` and
  `=restarting`;
* property stops for `vendor.per_mgr`, `vendor.per_proxy` and
  `qcamerasvr` to catch an explicit vendor-HAL start.

The policy allow is in `porting/policy/port-genfs-kgsl.cil`, the same
fragment that carries the KGSL genfscon.

## Verification after the next flash

1. `getprop init.svc.vendor.qrtr-ns` is `running`; `dmesg` has no
   `qrtr-ns: bind control socket: Permission denied` and no
   `avc: denied { net_admin }` for `qrtr-ns`.
2. `getprop init.svc.qcamerasvr` and `init.svc.vendor.per_mgr` are
   `stopped`/disabled; `init.svc.vendor.per_proxy` is stopped.
3. `init.svc.vendor.dataqti` is stopped and the `QTI_SDM_INFO` retry
   flood is gone.
4. `dmesg | grep 'process with updatable components'` has no entries;
   `sys.init.updatable_crashing` may still read `1` from an early boot
   transition, but `dmesg` must have no
   `flags_health_check UPDATABLE_CRASHING` exec.
5. The kernel QRTR NS remains active; the userspace daemon is the
   name-service peer on its own port.

This pass does not fix the camera stack.  Remove the `per_mgr` /
`qcamerasvr` overrides and add the `property_socket` allow when camera
work starts; remove the `dataqti` stop when the rmnet/MHI/modem data
path is brought up.
