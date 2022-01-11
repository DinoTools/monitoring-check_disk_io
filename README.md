check_disk_io - Monitor disk io
===============================

This is a monitoring plugin for [Icinga](https://icinga.com/), [Nagios](https://www.nagios.org/) and other compatible monitoring solutions to check the disk io.
It uses the psutil Python package to get the required information and should work with the following operating systems.

- Linux
- Windows
- macOS
- FreeBSD, OpenBSD, NetBSD
- Sun Solaris
- AIX

Requirements
------------

- [Python](https://www.python.org/) >= 3.6
- Python Packages
    - [psutil](https://pypi.org/project/psutil/)
    - [nagiosplugin](https://pypi.org/project/nagiosplugin/)

Installation
------------

### PIP

If you want to use pip we recommend to use as virtualenv to install the dependencies.

```shell
pip install -r requirements.txt
```

Copy the script ```check_disk_io.py``` into your plugin directory.

### Debian/Ubuntu

Install the required packages

```shell
sudo apt-get install python3 python3-nagiosplugin python3-psutil
```

Copy the script ```check_disk_io.py``` into your plugin directory.

Usage
-----

To get the latest help just run the following command.

```shell
./check_disk_io.py --help
```

Resources
---------

- Git-Repository: https://github.com/DinoTools/monitoring-check_disk_io
- Issues: https://github.com/DinoTools/monitoring-check_disk_io/issues

License
-------

GPLv3+
