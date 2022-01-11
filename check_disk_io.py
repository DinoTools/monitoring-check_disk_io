#!/usr/bin/env python3
# SPDX-FileCopyrightText: PhiBo DinoTools (2022)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
from datetime import datetime
import logging
from typing import Optional

import nagiosplugin
import psutil

logger = logging.getLogger('nagiosplugin')


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

    def __init__(self, disk_name: str):
        super().__init__()

        self.disk_name = disk_name

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
                name=f"{self.disk_name}.{value_name}",
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
                        name=f"{self.disk_name}.{value_name}_rate",
                        value=value,
                        uom=value_uom_mappings.get(f"{value_name}_rate"),
                        min=value_min_mappings.get(f"{value_name}_rate", 0),
                        max=value_max_mappings.get(f"{value_name}_rate"),
                    )
                except MissingValue as e:
                    logger.debug(f"{e}", exc_info=e)
            cookie["last_time"] = cur_time.timetuple()


def main():
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument(
        "-d",
        "--disk",
        required=True,
        help="Name of the disk",
        metavar="NAME"
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

    disk_name = args.disk
    check = nagiosplugin.Check(
        DiskIOResource(
            disk_name=disk_name
        )
    )

    for argument_name, argument_config in argument_mappings.items():
        extra_kwargs = {}
        if "fmt_metric" in argument_config:
            extra_kwargs["fmt_metric"] = argument_config["fmt_metric"]

        context_class = argument_config.get("class", nagiosplugin.ScalarContext)
        check.add(context_class(
            name=f"{disk_name}.{argument_name}",
            warning=getattr(args, f"warning_{argument_name}"),
            critical=getattr(args, f"critical_{argument_name}"),
            **extra_kwargs
        ))

    check.main(verbose=args.verbose)


if __name__ == "__main__":
    main()
