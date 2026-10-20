# QRTR service override: the treble boundary, 2026-10-20

## Symptom

`vendor.qrtr-ns` still exits with status 1 on `run305`, even though the
pre-policy overlay in `/system/etc/init/flags_health_check.rc` contains

```text
service vendor.qrtr-ns /vendor/bin/qrtr-ns -f
    class core
    user vendor_qrtr
    group vendor_qrtr
    capabilities NET_BIND_SERVICE NET_ADMIN
    override
```

The overlay is installed and parsed: `sys.init.updatable_crashing=1` while
`dmesg` contains no `flags_health_check` exec, so the filtered system file
is the one init read.

## Evidence

The running service has only the old capability set:

```text
$ su -c 'start vendor.qrtr-ns; ... cat /proc/$(pidof qrtr-ns)/status'
Uid:	2906	2906	2906	2906
Gid:	2906	2906	2906	2906
CapInh:	0000000000000400
CapPrm:	0000000000000400
CapEff:	0000000000000400
CapBnd:	0000000000000400
CapAmb:	0000000000000400
```

`0x400` is `CAP_NET_BIND_SERVICE`; the appended definition asks for
`0x1400` (`NET_BIND_SERVICE | NET_ADMIN`).  The vendor definition is still
the one in use:

```text
/vendor/etc/init/hw/init.qcom.rc:405 service vendor.qrtr-ns /vendor/bin/qrtr-ns -f
/vendor/etc/init/hw/init.qcom.rc:409     capabilities NET_BIND_SERVICE
```

## Why the override was rejected

AOSP `system/core/init/service_parser.cpp` rejects an override when the
new service and the old one come from different treble subcontexts:

```text
Service* old_service = service_list_->FindService(service_->name());
if (old_service) {
    if (!service_->is_override()) { ... duplicate ... }
    ...
    std::string context = service_->subcontext() ? service_->subcontext()->context() : "";
    std::string old_context = old_service->subcontext() ? old_service->subcontext()->context() : "";
    if (context != old_context) {
        return Error() << "service '" << service_->name()
                       << "' overrides another service across the treble boundary.";
    }
}
```

`ServiceParser::ParseSection` attaches a subcontext only when the file path
matches the vendor subcontext's prefixes (`/vendor`, `/odm`):

```text
Subcontext* restart_action_subcontext = nullptr;
if (subcontext_ && subcontext_->PathMatchesSubcontext(filename)) {
    restart_action_subcontext = subcontext_;
}
```

So `flags_health_check.rc` (system) has an empty subcontext, while the
existing `vendor.qrtr-ns` (vendor) belongs to `u:r:vendor_init:s0`.  The
override is parsed, found to cross the boundary, and discarded.  The
system-side file still works for actions, which is why the health-check
filter and the camera/dataqti `stop` actions are effective.

## Fix

Append the service override to a file that is actually in
`/vendor/etc/init`:

```text
service vendor.qrtr-ns /vendor/bin/qrtr-ns -f
    class core
    user vendor_qrtr
    group vendor_qrtr
    capabilities NET_BIND_SERVICE NET_ADMIN
    override
```

The initramfs guard writes `/vendor/etc/init/qcrild.rc` plus that block to
a memfd and bind-mounts it read-only before policy load.  `qcrild.rc` is in
the vendor directory scan, so it is parsed after the `hw/init.qcom.rc`
definition and in the same vendor subcontext.  The old definition is
replaced, not duplicated.

The system-side `flags_health_check.rc` keeps only actions; its previous
service definitions for `vendor.qrtr-ns`, `vendor.per_mgr` and
`qcamerasvr` were all cross-boundary and ineffective.

## Verification after boot

```text
su -c 'cat /vendor/etc/init/qcrild.rc'          # has the appended block
su -c 'start vendor.qrtr-ns; sleep 1'
getprop init.svc.vendor.qrtr-ns                 # running, not restarting
su -c 'pidof qrtr-ns'                           # pick the pid
su -c 'grep CapEff /proc/<pid>/status'          # 0000000000001400
su -c 'dmesg | grep -i avc | tail'              # no net_admin denial
```

If the service is still `restarting` with `CapEff=0x400`, the vendor
overlay lost the race with the vendor directory scan; the fix is to install
it earlier, not to add capabilities to the system-side file.
