#!/bin/bash
# proxmox_lxc_setup.sh
# ¡Ejecuta este script DIRECTAMENTE en la consola SSH de tu nodo Proxmox!
#
# Este script crea automágicamente un contenedor LXC en Proxmox, 
# le asigna 4GB de RAM y 2 vCPUs, y preinstala Python 3.11 y FFmpeg.

set -e

# ==== CONFIGURACIÓN DEL CONTENEDOR ====
# Puedes cambiar el ID de contenedor pasándolo como argumento: ./proxmox_lxc_setup.sh 205
CTID=${1:-"200"} 
HOSTNAME="uxai-ugc-agent"
RAM=4096             # 4GB (Requeridos por FFmpeg y la gestión de memoria)
CORES=2              # 2 vCPUs
DISK="20G"           # 20GB de disco para el OS y los videos generados
STORAGE="local-lvm"  # Almacenamiento por defecto en Proxmox
NETWORK="name=eth0,bridge=vmbr0,ip=dhcp" # Red en DHCP por defecto
PASSWORD="changeme123" # Contraseña de root para el LXC

echo "=========================================================="
echo " Inicializando Creación Automática de LXC en Proxmox"
echo " Contenedor ID: $CTID | Hostname: $HOSTNAME"
echo "=========================================================="

# 1. Buscar una plantilla de Ubuntu 22.04 existente en Proxmox
echo "[+] Buscando plantilla de Ubuntu 22.04..."
TEMPLATE=$(pvesm list local -content vztmpl | grep ubuntu-22.04 | awk '{print $1}' | head -n 1)

if [ -z "$TEMPLATE" ]; then
    echo "[!] No se encontró ninguna plantilla de Ubuntu 22.04 en Proxmox."
    echo "[!] Descargando ubuntu-22.04-standard automáticamente..."
    pveam update
    pveam download local ubuntu-22.04-standard_22.04-1_amd64.tar.zst
    TEMPLATE=$(pvesm list local -content vztmpl | grep ubuntu-22.04 | awk '{print $1}' | head -n 1)
fi

echo "[+] Usando plantilla: $TEMPLATE"

# 2. Crear el contenedor usando 'pct'
echo "[+] Creando contenedor (Esto tomará unos segundos)..."
pct create $CTID $TEMPLATE \
    --hostname $HOSTNAME \
    --memory $RAM \
    --cores $CORES \
    --net0 $NETWORK \
    --storage $STORAGE \
    --rootfs $STORAGE:$DISK \
    --password $PASSWORD \
    --unprivileged 1 \
    --features nesting=1

# 3. Encender el contenedor
echo "[+] Encendiendo contenedor..."
pct start $CTID

echo "[+] Esperando 10 segundos a que la red obtenga IP por DHCP..."
sleep 10

# Extraer IP asignada (solo para mostrar)
IP_ASSIGNED=$(pct exec $CTID -- ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')

# 4. Instalar todas las dependencias (dentro del contenedor)
echo "[+] Instalando prerequisitos (Python 3.11, FFmpeg, Git) dentro del LXC..."
pct exec $CTID -- bash -c "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y"
pct exec $CTID -- bash -c "DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip python3.11-venv ffmpeg libgl1 git curl"

# 5. Clonar el repositorio
echo "[+] Clonando repositorio (si lo tienes en github, ajusta el URL)..."
pct exec $CTID -- bash -c "mkdir -p /opt && cd /opt && \
    git clone https://github.com/tu-usuario/auto-ugc.git || echo 'Repositorio no clonado. Recuerda clonar tu código manualmente en /opt/auto-ugc'"

echo "=========================================================="
echo " ¡LXC $CTID configurado con éxito!"
echo " IP Asignada: $IP_ASSIGNED"
echo " "
echo " 👉 Para entrar al contenedor desde Proxmox, usa:"
echo "      pct enter $CTID"
echo " "
echo " 👉 Una vez dentro del LXC, finaliza la instalación de Python con:"
echo "      cd /opt/auto-ugc/uxai-ugc-agent"
echo "      python3.11 -m venv venv"
echo "      source venv/bin/activate"
echo "      pip install -r requirements.txt"
echo "      cp .env.example .env"
echo " "
echo " ¡Listo! Ya estás preparado para correr el dashboard web."
echo "=========================================================="
