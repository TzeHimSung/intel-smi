#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time


WIDTH = 91
GPU_LEFT = 41
GPU_MID = 24
GPU_RIGHT = 22
METRIC_IDS = ",".join(str(i) for i in range(37))


DETAIL_FIELDS = [
    ("pci_bdf_address", "PCI Bus ID"),
    ("drm_device", "DRM Device"),
    ("pci_vendor_id", "PCI Vendor ID"),
    ("pci_device_id", "PCI Device ID"),
    ("uuid", "UUID"),
    ("device_stepping", "Stepping"),
    ("kernel_version", "Kernel"),
    ("driver_version", "Driver"),
    ("gfx_firmware_status", "GFX Firmware"),
    ("gfx_firmware_version", "GFX FW Version"),
    ("oprom_code_firmware_version", "OPROM Code"),
    ("core_clock_rate_mhz", "Max Core Clock"),
    ("memory_physical_size_byte", "Memory Total"),
    ("memory_free_size_byte", "Memory Free"),
    ("max_mem_alloc_size_byte", "Max Allocation"),
    ("memory_bus_width", "Memory Bus Width"),
    ("number_of_memory_channels", "Memory Channels"),
    ("number_of_eus", "EUs"),
    ("number_of_slices", "Slices"),
    ("number_of_sub_slices_per_slice", "Sub Slices/Slice"),
    ("number_of_threads_per_eu", "Threads/EU"),
    ("physical_eu_simd_width", "EU SIMD Width"),
    ("number_of_tiles", "Tiles"),
    ("number_of_media_engines", "Media Engines"),
    ("max_hardware_contexts", "HW Contexts"),
]


def run(cmd, timeout=12):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )


def load_json(cmd, default=None, timeout=12):
    proc = run(cmd, timeout=timeout)
    text = proc.stdout.strip()
    if not text:
        text = proc.stderr.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def shorten(value, width):
    text = str(value)
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def border(char="-"):
    return "+" + char * (WIDTH - 2) + "+"


def rule(char="="):
    return "|" + char * (WIDTH - 2) + "|"


def split_border(char="-"):
    return "+" + char * GPU_LEFT + "+" + char * GPU_MID + "+" + char * GPU_RIGHT + "+"


def split_rule(char="="):
    return "|" + char * GPU_LEFT + "+" + char * GPU_MID + "+" + char * GPU_RIGHT + "|"


def split_row(left="", middle="", right="", right_align=False):
    right_text = shorten(right, GPU_RIGHT)
    if right_align:
        right_text = right_text.rjust(GPU_RIGHT)
    else:
        right_text = right_text.ljust(GPU_RIGHT)
    return (
        "|"
        + shorten(left, GPU_LEFT).ljust(GPU_LEFT)
        + "|"
        + shorten(middle, GPU_MID).ljust(GPU_MID)
        + "|"
        + right_text
        + "|"
    )


def row(text=""):
    return "| " + shorten(text, WIDTH - 4).ljust(WIDTH - 4) + " |"


def kv_row(key, value, key_width=30):
    text = f"{shorten(key, key_width):<{key_width}} {value}"
    return row(text)


def fmt_bytes(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    idx = 0
    while number >= 1024 and idx < len(units) - 1:
        number /= 1024
        idx += 1
    if idx == 0:
        return f"{int(number)} {units[idx]}"
    return f"{number:.2f} {units[idx]}"


def fmt_detail_value(key, value):
    if value in (None, ""):
        return "N/A"
    if key.endswith("_byte"):
        return fmt_bytes(value)
    if key.endswith("_mhz"):
        return f"{value} MHz"
    if key == "memory_bus_width":
        return f"{value} bit"
    return str(value)


def parse_cli_version(text):
    version = "unknown"
    build = "unknown"
    level_zero = "unknown"
    in_cli = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "CLI:":
            in_cli = True
            continue
        if stripped == "Service:":
            in_cli = False
        if in_cli and stripped.startswith("Version:"):
            version = stripped.split(":", 1)[1].strip()
        if in_cli and stripped.startswith("Build ID:"):
            build = stripped.split(":", 1)[1].strip()
        if stripped.startswith("Level Zero Version:"):
            level_zero = stripped.split(":", 1)[1].strip()
    return version, build, level_zero


def parse_dump(stdout):
    lines = [line.rstrip("\n") for line in stdout.splitlines()]
    header_index = None
    for index, line in enumerate(lines):
        if line.startswith("Timestamp,"):
            header_index = index
            break
    if header_index is None:
        return {}, []

    reader = csv.reader(lines[header_index:])
    try:
        headers = [item.strip() for item in next(reader)]
    except StopIteration:
        return {}, []

    for raw_row in reader:
        if not raw_row:
            continue
        values = [item.strip() for item in raw_row]
        data = {}
        for index, header in enumerate(headers):
            data[header] = values[index] if index < len(values) else ""
        return data, headers
    return {}, headers


def get_dump(device_id):
    proc = run(["xpu-smi", "dump", "-d", str(device_id), "-m", METRIC_IDS, "-n", "1"], timeout=20)
    data, headers = parse_dump(proc.stdout + "\n" + proc.stderr)
    return data, headers, proc.stderr


def safe_float(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fmt_metric(label, value):
    if value in (None, "", "N/A"):
        return "N/A"
    number = safe_float(value)
    if number is None:
        return str(value)

    if "%" in label:
        return f"{number:.2f} %"
    if "(W)" in label:
        return f"{number:.2f} W"
    if "(MHz)" in label:
        return f"{number:.0f} MHz"
    if "(MiB)" in label:
        return f"{number:.2f} MiB"
    if "(kB/s)" in label:
        return f"{number:.0f} kB/s"
    if "(J)" in label:
        return f"{number:.2f} J"
    if "Temperature" in label or "Celsius" in label:
        return f"{number:.0f} C"
    return f"{number:g}"


def compact_number(value):
    number = safe_float(value)
    if number is None:
        return None
    return number


def compact_temp(value):
    number = compact_number(value)
    if number is None:
        return "N/A"
    return f"{number:.0f}C"


def compact_watts(value):
    number = compact_number(value)
    if number is None:
        return "N/A"
    return f"{number:.0f}W"


def compact_percent(value):
    number = compact_number(value)
    if number is None:
        return "N/A"
    return f"{number:.0f}%"


def compact_mib(value):
    number = compact_number(value)
    if number is None:
        return "N/A"
    return f"{number:.0f}MiB"


def format_bus(bus):
    if not bus or bus == "N/A":
        return "N/A"
    if re.match(r"^[0-9a-fA-F]{4}:", str(bus)):
        return "0000" + str(bus)
    return str(bus)


def display_device_name(detail, device):
    name = detail.get("device_name") or device.get("device_name") or "Unknown"
    pci_id = str(detail.get("pci_device_id") or device.get("pci_device_id") or "").lower()
    if pci_id == "0xe212" or "0xe212" in name.lower():
        return "Intel Arc Pro B50"
    return name


def drm_short_name(drm):
    if not drm:
        return "N/A"
    return os.path.basename(str(drm))


def perf_state(detail, dump):
    current = compact_number(dump.get("GPU Frequency (MHz)"))
    max_clock = compact_number(detail.get("core_clock_rate_mhz"))
    if current is None:
        return "P?"
    if max_clock and current >= max_clock * 0.8:
        return "P0"
    if current >= 1000:
        return "P2"
    if current > 0:
        return "P8"
    return "P?"


def memory_total_mib(detail):
    raw = detail.get("memory_physical_size_byte")
    number = safe_float(raw)
    if number is None:
        return None
    return number / (1024 * 1024)


def pct_bar(value, width=14):
    number = safe_float(value)
    if number is None:
        return "[" + "?" * width + "]"
    number = max(0.0, min(100.0, number))
    filled = round((number / 100.0) * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def process_rows():
    data = load_json(["xpu-smi", "ps", "-j"], default=None, timeout=8)
    rows = []
    if isinstance(data, dict):
        for item in data.get("device_util_by_proc_list", []) or []:
            rows.append(item)
    return rows


def render_processes():
    rows = process_rows()
    output = [
        border(),
        row("Processes:"),
        row(f"{'GPU':>5}   {'GI':<3}  {'CI':<3} {'PID':>15} {'Type':>6}   {'Process name':<32} {'GPU Memory':>10}"),
        row(f"{'':>5}   {'ID':<3}  {'ID':<3} {'':>15} {'':>6}   {'':<32} {'Usage':>10}"),
        rule("="),
    ]
    if not rows:
        output.append(row("No running processes found"))
    else:
        for item in rows:
            gpu = item.get("device_id", item.get("deviceId", "N/A"))
            pid = item.get("process_id", item.get("pid", "N/A"))
            name = item.get("process_name", item.get("command", item.get("process", "N/A")))
            mem = item.get("mem_size", item.get("memory", item.get("mem", "N/A")))
            output.append(row(f"{str(gpu):>5}   {'N/A':<3}  {'N/A':<3} {str(pid):>15} {'C':>6}   {shorten(name, 32):<32} {str(mem):>10}"))
    output.append(border())
    return output


def get_details(devices):
    details = {}
    for device in devices:
        device_id = device.get("device_id")
        detail = load_json(["xpu-smi", "discovery", "-d", str(device_id), "-j"], default={}, timeout=12)
        if not isinstance(detail, dict):
            detail = {}
        merged = dict(device)
        merged.update(detail)
        details[device_id] = merged
    return details


def render_summary(version, build, level_zero, devices, details, dumps):
    now = dt.datetime.now()
    timestamp = now.strftime("%a %b %d %H:%M:%S %Y").replace(" 0", "  ")
    kernel = "N/A"
    if details:
        kernel = next(iter(details.values())).get("kernel_version") or "N/A"

    output = [
        timestamp,
        border(),
        row(f"Intel-SMI {version:<19} Build ID: {build:<10} Level Zero Version: {level_zero}"),
        split_border(),
        split_row(" GPU  Name                    Driver", " Bus-Id          DRM", " Volatile Uncorr. ECC"),
        split_row(" Fan  Temp   Perf          Pwr:Usage/Cap", "           Memory-Usage", " GPU-Util  Compute M."),
        split_row("", "", "Throttle", right_align=True),
        split_rule("="),
    ]

    for index, device in enumerate(devices):
        device_id = device.get("device_id")
        detail = details.get(device_id, {})
        dump = dumps.get(device_id, {})
        name = display_device_name(detail, device)
        bus = format_bus(detail.get("pci_bdf_address") or "N/A")
        drm = drm_short_name(detail.get("drm_device"))
        driver = "xe"
        temp = compact_temp(dump.get("GPU Core Temperature (Celsius Degree)"))
        power = compact_watts(dump.get("GPU Power (W)"))
        util = compact_percent(dump.get("Average % utilization of all GPU Engines"))
        perf = perf_state(detail, dump)
        throttle = dump.get("Throttle reason") or "N/A"
        total = memory_total_mib(detail)
        mem_used = compact_mib(dump.get("GPU Memory Used (MiB)"))
        if total is not None and mem_used != "N/A":
            mem = f"{mem_used:>8} / {total:.0f}MiB"
        elif mem_used != "N/A":
            mem = f"{mem_used:>8} /      N/A"
        else:
            mem = "     N/A /      N/A"
        power_pair = f"{power:>7} /   N/A"
        left_name = f"{str(device_id):>4}  {shorten(name, 25):<25} {driver:>6}"
        left_stats = f"{'N/A':>4} {temp:>5} {perf:>6} {power_pair:>20}"
        middle_bus = f" {shorten(bus, 16):<16} {shorten(drm, 5):>5}"
        middle_mem = f"{mem:>24}"
        right_ecc = f"{'N/A':>22}"
        right_util = f"{util:>7}      Default"
        right_throttle = shorten(throttle, GPU_RIGHT).rjust(GPU_RIGHT)

        if index:
            output.append(split_border())
        output.append(split_row(left_name, middle_bus, right_ecc, right_align=True))
        output.append(split_row(left_stats, middle_mem, right_util, right_align=True))
        output.append(split_row("", "", right_throttle, right_align=True))

    output.append(split_border())
    return output


def render_detail(device_id, detail):
    output = [border(), row(f"GPU {device_id} Device Details"), border()]
    for key, label in DETAIL_FIELDS:
        if key in detail:
            output.append(kv_row(label, fmt_detail_value(key, detail.get(key))))
    output.append(border())
    return output


def render_telemetry(device_id, dump, headers):
    output = [border(), row(f"GPU {device_id} Telemetry"), border()]
    if not dump:
        output.append(row("No telemetry data available"))
        output.append(border())
        return output

    metric_items = []
    for header in headers:
        if header in ("Timestamp", "DeviceId"):
            continue
        metric_items.append((header, fmt_metric(header, dump.get(header))))

    output.append(row(f"Sample: {dump.get('Timestamp', 'N/A')}"))
    metric_width = 28
    value_width = 11
    output.append(row(f"{'Metric':<{metric_width}} {'Value':>{value_width}}   {'Metric':<{metric_width}} {'Value':>{value_width}}"))
    output.append(border())
    for index in range(0, len(metric_items), 2):
        left = metric_items[index]
        right = metric_items[index + 1] if index + 1 < len(metric_items) else ("", "")
        left_text = f"{shorten(left[0], metric_width):<{metric_width}} {shorten(left[1], value_width):>{value_width}}"
        right_text = f"{shorten(right[0], metric_width):<{metric_width}} {shorten(right[1], value_width):>{value_width}}"
        output.append(row(f"{left_text}   {right_text}"))

    mem_util = dump.get("GPU Memory Utilization (%)")
    gpu_util = dump.get("Average % utilization of all GPU Engines")
    if mem_util not in (None, "", "N/A") or gpu_util not in (None, "", "N/A"):
        output.append(border())
        output.append(row(f"GPU Util {pct_bar(gpu_util)}   Memory Util {pct_bar(mem_util)}"))

    output.append(border())
    return output


def should_show_sudo_note(dumps, stderr_by_device):
    if os.geteuid() == 0:
        return False
    warning_seen = any("Elevated privileges required" in stderr for stderr in stderr_by_device.values())
    if warning_seen:
        return True
    important = [
        "GPU Core Temperature (Celsius Degree)",
        "Average % utilization of all GPU Engines",
        "Memory Read (kB/s)",
    ]
    for dump in dumps.values():
        if any(dump.get(key) == "N/A" for key in important):
            return True
    return False


def render_once(args):
    xpu_smi = shutil.which("xpu-smi")
    if not xpu_smi:
        return "xpu-smi not found in PATH\n"

    version_text = run(["xpu-smi", "-v"], timeout=8).stdout
    version, build, level_zero = parse_cli_version(version_text)
    discovery = load_json(["xpu-smi", "discovery", "-j"], default={}, timeout=12)
    devices = discovery.get("device_list", []) if isinstance(discovery, dict) else []
    if args.device is not None:
        devices = [device for device in devices if str(device.get("device_id")) == str(args.device)]

    if not devices:
        return "No Intel XPU devices discovered\n"

    details = get_details(devices)
    dumps = {}
    headers_by_device = {}
    stderr_by_device = {}
    for device in devices:
        device_id = device.get("device_id")
        dump, headers, stderr = get_dump(device_id)
        dumps[device_id] = dump
        headers_by_device[device_id] = headers
        stderr_by_device[device_id] = stderr

    output = []
    output.extend(render_summary(version, build, level_zero, devices, details, dumps))

    show_details = args.details or args.full
    show_telemetry = args.telemetry or args.full

    if show_telemetry and should_show_sudo_note(dumps, stderr_by_device):
        output.append(row("Note: run `sudo intel-smi` for full MEI telemetry such as temperature and engine utilization."))
        output.append(border("="))
    if show_details or show_telemetry:
        for device in devices:
            device_id = device.get("device_id")
            if show_details:
                output.extend(render_detail(device_id, details.get(device_id, {})))
            if show_telemetry:
                output.extend(render_telemetry(device_id, dumps.get(device_id, {}), headers_by_device.get(device_id, [])))
    if not args.no_processes:
        output.append("")
        output.extend(render_processes())
    return "\n".join(output) + "\n"


def main():
    parser = argparse.ArgumentParser(description="nvidia-smi style view for Intel XPU-SMI")
    parser.add_argument("-d", "--device", help="Only show one device id")
    parser.add_argument("-l", "--loop", type=float, help="Refresh every N seconds")
    parser.add_argument("--details", action="store_true", help="Show hardware/firmware details")
    parser.add_argument("--telemetry", action="store_true", help="Show all raw telemetry metrics")
    parser.add_argument("--full", "--all", dest="full", action="store_true", help="Show details and telemetry")
    parser.add_argument("--no-processes", action="store_true", help="Hide process table")
    args = parser.parse_args()

    if args.loop:
        while True:
            print("\033[2J\033[H", end="")
            print(render_once(args), end="")
            time.sleep(max(0.5, args.loop))
    else:
        print(render_once(args), end="")


if __name__ == "__main__":
    main()
