# intel-smi

`intel-smi` is a small `nvidia-smi`-style terminal dashboard for Intel GPUs.
It wraps Intel's official `xpu-smi` command and renders the useful parts in a
compact table: device status, memory usage, utilization, throttling state, and
active GPU processes.

The tool was originally built for an Intel Arc Pro B50 on Fedora, but it should
work with any Intel GPU that is visible to `xpu-smi`.

## Features

- `nvidia-smi`-inspired default layout.
- One-line install, no Python package dependencies.
- Shows GPU summary and active processes by default.
- Optional detailed hardware and telemetry tables.
- Loop mode for live monitoring.
- Friendly B50 alias via `b50-smi`.

## Requirements

- Linux.
- Python 3.9 or newer.
- Intel `xpu-smi` available in `PATH`.
- Intel GPU runtime stack working well enough for:
  - `xpu-smi discovery -j`
  - `xpu-smi dump ...`
  - `xpu-smi ps -j`

For full telemetry such as temperature, engine utilization, PCIe throughput, and
some memory counters, run with `sudo`. These metrics may require access to MEI
devices such as `/dev/mei0`.

This project does not install GPU drivers or Intel XPU-SMI itself. Install those
with the packages appropriate for your distribution first.

## Install

Clone the repository and run the installer:

```bash
git clone git@github.com:TzeHimSung/intel-smi.git
cd intel-smi
sudo ./install.sh
```

By default this installs:

- `/usr/local/bin/intel-smi`
- `/usr/local/bin/b50-smi` as a symlink to `intel-smi`

To install somewhere else:

```bash
sudo PREFIX=/opt/intel-smi ./install.sh
```

## Usage

Default view:

```bash
intel-smi
```

Recommended full telemetry view:

```bash
sudo intel-smi
```

Use the B50-friendly alias:

```bash
sudo b50-smi
```

Refresh every second:

```bash
sudo intel-smi -l 1
```

Only show one device:

```bash
intel-smi -d 0
```

Show hardware and firmware details:

```bash
intel-smi --details
```

Show raw telemetry metrics:

```bash
sudo intel-smi --telemetry
```

Show everything:

```bash
sudo intel-smi --full
```

Hide the process table:

```bash
intel-smi --no-processes
```

## Example

```text
Sat Jun  6 17:24:12 2026
+-----------------------------------------------------------------------------------------+
| Intel-SMI 1.3.7.20260530      Build ID: 9fc2535d   Level Zero Version: 1.24.2           |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                    Driver     | Bus-Id          DRM    | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |              Throttle|
|=========================================+========================+======================|
|   0  Intel Arc Pro B50             xe   | 00000000:03:00.0 card1 |                   N/A|
| N/A   50C     P2          30W /   N/A   |       396MiB / 16304MiB|       0%      Default|
|                                         |                        |         Not Throttled|
+-----------------------------------------+------------------------+----------------------+
```

## Notes

- The displayed `Perf` state is inferred from the current GPU frequency because
  Intel XPU-SMI does not expose an NVIDIA-style performance state.
- The power cap column is shown as `N/A` unless XPU-SMI exposes a stable cap
  value for the device.
- The process table is only as complete as `xpu-smi ps -j`. Some Level
  Zero/oneAPI workloads on Arc Pro B50 with the `xe` driver, including Ollama's
  oneAPI runner, may show GPU offload in the application while `xpu-smi ps -j`
  reports no process rows.
- Intel Arc Pro B50 currently appears as `Intel(R) Graphics [0xe212]` in
  `xpu-smi`; `intel-smi` maps that PCI ID to `Intel Arc Pro B50` for readability.

## License

MIT
