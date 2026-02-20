# auto-ugc

> Auto UGC — automated user-generated content pipeline.

## Overview

This project automates the creation and distribution of user-generated content (UGC).

## Getting Started

_Documentation coming soon._

### Proxmox LXC Automated Setup

If you are running this on a Proxmox node, you can use the provided `proxmox_lxc_setup.sh` script to automatically create and configure a lightweight LXC container with all dependencies necessary (4GB RAM, 2 Cores, Python 3.11, and FFmpeg) for Auto-UGC.

1. SSH into your Proxmox server as root.
2. Run the script (you may pass a preferred Container ID, default is 200). Note that you should upload the script to the root of your Proxmox first, or directly paste its contents.

```bash
# Set execution permissions
chmod +x proxmox_lxc_setup.sh

# Run the script (Example with Container ID 205)
./proxmox_lxc_setup.sh 205
```

3. Once the automatic setup completes, enter your new container to start the dashboard:
```bash
pct enter 205
cd /opt/auto-ugc/uxai-ugc-agent
source venv/bin/activate
# Fill .env according to .env.example
python main.py --web
```

## License

MIT
