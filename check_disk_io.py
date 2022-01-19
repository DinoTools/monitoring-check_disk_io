#!/usr/bin/env python3
# SPDX-FileCopyrightText: PhiBo DinoTools (2022)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
from datetime import datetime
import logging
import os
import re
from typing import Optional

import nagiosplugin
import psutil

logger = logging.getLogger("nagiosplugin")


class MissingValue(ValueError):
    pass


class BooleanContext(nagiosplugin.Context):
    def performance(self, metric, resource):
        return nagiosplugin.performance.Performance(
            label=metric.name,
            value=1 if metric.value else 0
        )


class DiskIOResource(nagiosplugin.Resource):
    name = "DISK IO"

    def __init__(self, disk_name: str, display_name: str):
        super().__init__()

        self.disk_name = disk_name
        self.display_name = display_name

    @staticmethod
    def _calc_rate(
            cookie: nagiosplugin.Cookie,
            name: str,
            cur_value: int,
            elapsed_seconds: float,
            factor: int
    ) -> float:
        old_value: Optional[int] = cookie.get(name)
        cookie[name] = cur_value
        if old_value is None:
            raise MissingValue(f"Unable to find old value for '{name}'")
        if elapsed_seconds is None:
            raise MissingValue("Unable to get elapsed seconds")
        return (cur_value - old_value) / elapsed_seconds * factor

    def probe(self):
        cur_time = datetime.now()
        disks_counters = psutil.disk_io_counters(perdisk=True)

        disk_counters = disks_counters[self.disk_name]

        value_name_mappings = {
            "read_count": None,
            "write_count": None,
            "read_bytes": None,
            "write_bytes": None,
            "read_time": None,
            "write_time": None,
            "read_merged_count": None,
            "write_merged_count": None,
            "busy_time": None,
        }
        value_uom_mappings = {
            "read_bytes": "B",
            "write_bytes": "B",
            "read_merged_count": "c",
            "write_merged_count": "c",
        }
        value_factor_mappings = {}
        value_min_mappings = {}
        value_max_mappings = {}
        values = {}
        for value_name, attr_name in value_name_mappings.items():
            if attr_name is None:
                attr_name = value_name
            values[value_name] = getattr(disk_counters, attr_name)
            yield nagiosplugin.Metric(
                name=f"{self.display_name}.{value_name}",
                value=values[value_name],
                uom=value_uom_mappings.get(value_name),
            )
        with nagiosplugin.Cookie(f"/tmp/check_disk_io_{self.disk_name}.data") as cookie:
            last_time_tuple = cookie.get("last_time")
            elapsed_seconds = None
            if isinstance(last_time_tuple, (list, tuple)):
                last_time = datetime(*last_time_tuple[0:6])
                delta_time = cur_time - last_time
                elapsed_seconds = delta_time.total_seconds()

            for value_name in value_name_mappings.keys():
                try:
                    value = self._calc_rate(
                        cookie=cookie,
                        name=value_name,
                        cur_value=values[value_name],
                        elapsed_seconds=elapsed_seconds,
                        factor=value_factor_mappings.get(f"{value_name}_rate", 1)
                    )
                    yield nagiosplugin.Metric(
                        name=f"{self.display_name}.{value_name}_rate",
                        value=value,
                        uom=value_uom_mappings.get(f"{value_name}_rate"),
                        min=value_min_mappings.get(f"{value_name}_rate", 0),
                        max=value_max_mappings.get(f"{value_name}_rate"),
                    )
                except MissingValue as e:
                    logger.debug(f"{e}", exc_info=e)
            cookie["last_time"] = cur_time.timetuple()


@nagiosplugin.guarded()
def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument(
        "-d",
        "--disk",
        dest="disks",
        required=True,
        help="Name of the disk",
        metavar="NAME",
        action="append",
    )

    argp.add_argument(
        "--disk-exclude",
        dest="disk_excludes",
        help="Name of the disk to exclude",
        metavar="NAME",
        action="append",
        default=[],
    )

    argp.add_argument(
        "--regex",
        default=False,
        help="Treat disk names as regex pattern",
        action="store_true",
    )

    argp.add_argument(
        "--show-mountpoint",
        default=False,
        help="Try to resolve and report the mountpoint instead of the device name. (only: Linux)",
        action="store_true",
    )

    argp.add_argument(
        "--use-mountpoint",
        default=False,
        help="Try to resolve and use the mountpoint instead of the device name for the disk option. (only: Linux)",
        action="store_true",
    )

    argument_mappings = {
        "read_count": {
            "help": "Total count of read operations"
        },
        "write_count": {
            "help": "Total count of write operations"
        },
        "read_bytes": {
            "help": "Sum of bytes read"
        },
        "write_bytes": {
            "help": "Sum of bytes written"
        },
        "read_time": {
            "help": "Number of seconds the system has spend reading data"
        },
        "write_time": {
            "help": "Number of seconds the system has spend writing data"
        },
        "read_merged_count": {
            "help": "Total count of read operations that could be merged into one operation"
        },
        "write_merged_count": {
            "help": "Total count of write operations that could be merged into one operation"
        },
        "busy_time": {
            "help": "Number of seconds the system has spend being busy reading data from disk"
        },

        "read_count_rate": {
            "help": "Number of read operations per second"
        },
        "write_count_rate": {
            "help": "Number of write operations per second"
        },
        "read_bytes_rate": {
            "help": "Throughput of read bytes per second"
        },
        "write_bytes_rate": {
            "help": "Throughput of written bytes per second"
        },
        "read_time_rate": {
            "help": "How many seconds are spend reading data per second"
        },
        "write_time_rate": {
            "help": "How many seconds are spend writing data per second"
        },
        "read_merged_count_rate": {
            "help": "How many read operations could be merged per second"
        },
        "write_merged_count_rate": {
            "help": "How many write operations could be merged per second"
        },
        "busy_time_rate": {
            "help": "How many seconds the system has been busy doing io stuff per second"
        },
    }

    for argument_name, argument_config in argument_mappings.items():
        for argument_type in ("warning", "critical"):
            argp.add_argument(
                f"--{argument_type}-{argument_name.replace('_', '-')}",
                dest=f"{argument_type}_{argument_name}",
                help=argument_config.get("help"),
                default=argument_config.get("default"),
            )

    argp.add_argument('-v', '--verbose', action='count', default=0)
    args = argp.parse_args()

    runtime = nagiosplugin.Runtime()
    runtime.verbose = args.verbose

    disk_names = set()
    available_disk_names = psutil.disk_io_counters(perdisk=True).keys()
    logger.debug(f"Available disks: {', '.join(available_disk_names)}")

    device_mountpont_mappings = dict([(disk_name, disk_name) for disk_name in available_disk_names])
    if args.use_mountpoint or args.show_mountpoint:
        if psutil.LINUX:
            device_mountpoint = []
            for partition in psutil.disk_partitions():
                device_shortname = os.path.basename(os.path.realpath(partition.device))
                logger.debug(f"Resolved display_name for device '{device_shortname}' to '{partition.mountpoint}'")
                device_mountpoint.append((device_shortname, partition.mountpoint))
            # We sort the devices and mountpoints to have a predictive order
            device_mountpont_mappings = dict(sorted(device_mountpoint))

    logger.debug(f"Disk patterns/names: {', '.join(args.disks)}")
    logger.debug("Regex: {status}".format(status="enabled" if args.regex else "disabled"))

    # First add all matching disks to the list ...
    for disk_name_pattern in args.disks:
        if args.regex:
            regex = re.compile(disk_name_pattern)
            for disk_name, mountpoint in device_mountpont_mappings.items():
                if (
                    not args.use_mountpoint and regex.match(disk_name) or
                    args.use_mountpoint and regex.match(mountpoint)
                ):
                    disk_names.add(disk_name)
        else:
            for disk_name, mountpoint in device_mountpont_mappings.items():
                if (
                    not args.use_mountpoint and disk_name == disk_name_pattern or
                    args.use_mountpoint and mountpoint == disk_name_pattern
                ):
                    disk_names.add(disk_name)

    logger.debug(f"Disk exclude patterns/names: {', '.join(args.disk_excludes)}")
    # ... than remove all excluded from the list
    for disk_name_pattern in args.disk_excludes:
        if args.regex:
            regex = re.compile(disk_name_pattern)
            for disk_name, mountpoint in device_mountpont_mappings.items():
                if (
                    not args.use_mountpoint and regex.match(disk_name) or
                    args.use_mountpoint and regex.match(mountpoint)
                ):
                    disk_names.remove(disk_name)
        else:
            for disk_name, mountpoint in device_mountpont_mappings.items():
                if (
                    not args.use_mountpoint and disk_name == disk_name_pattern or
                    args.use_mountpoint and mountpoint == disk_name_pattern
                ):
                    disk_names.remove(disk_name)

    logger.debug(f"Matching disks: {' '.join(disk_names)}")

    check = nagiosplugin.Check()
    for disk_name in disk_names:
        if args.show_mountpoint:
            display_name = device_mountpont_mappings[disk_name]
        else:
            display_name = disk_name

        check.add(DiskIOResource(
            disk_name=disk_name,
            display_name=display_name,
        ))
        for argument_name, argument_config in argument_mappings.items():
            extra_kwargs = {}
            if "fmt_metric" in argument_config:
                extra_kwargs["fmt_metric"] = argument_config["fmt_metric"]

            context_class = argument_config.get("class", nagiosplugin.ScalarContext)
            check.add(context_class(
                name=f"{display_name}.{argument_name}",
                warning=getattr(args, f"warning_{argument_name}"),
                critical=getattr(args, f"critical_{argument_name}"),
                **extra_kwargs
            ))

    check.main(verbose=args.verbose)


if __name__ == "__main__":
    main()
