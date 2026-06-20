# DeluxeCHD

A clean, native utility designed to batch extract zipped PS1 games, convert them to highly optimized CHD format using `chdman`, and optionally repackage or clean up original files.

## Prerequisites

Ensure your host system has the underlying base compression utilities installed locally:

```bash
# Ubuntu/Debian
sudo apt install mame-tools unzip zip

# Arch Linux
sudo pacman -S mame-tools unzip zip