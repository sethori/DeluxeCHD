# DeluxeCHD

A clean, native utility designed to batch extract zipped PS1 games, convert them to highly optimized CHD format using `chdman`, and optionally repackage or clean up original files.

## Prerequisites

Ensure your host system has the underlying base compression utilities installed locally:

```bash
# Ubuntu/Debian
sudo apt install mame-tools unzip zip

# Arch Linux
sudo pacman -S mame-tools unzip zip
```

## Installation

You can install DeluxeCHD using our automated installer script. The script automatically handles downloading the pre-compiled binary, placing it in your users path, and creating a native Linux application menu shortcut with the correct branding icon.

Automatic Installation
Run this command in your terminal to automatically pull down the latest version and configure your system:

```bash
curl -sSL https://raw.githubusercontent.com/sethori/DeluxeCHD/main/install.sh | bash
```

Manual Installation
Run this if you git clone the repo without running the curl script above.

```bash
# Make the script executable
chmod +x install.sh

# Run the installer
./install.sh
```
