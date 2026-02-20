#!/bin/bash
# lxc_wrapper.sh
# Helper script to wrap the creation and configuration of an LXC container
# for the auto-ugc (uxai-ugc-agent) project.
# 
# Nota: Asumo que "lcx" se refería a "lxc" (Linux Containers).

set -e

CONTAINER_NAME="ugc-agent"
IMAGE="ubuntu:22.04"
MEMORY_LIMIT="4GB"  # Según la recomendación del README (VM Setup Target: 4GB RAM)
CPU_LIMIT="2"
PROJECT_DIR="uxai-ugc-agent"

echo "============================================="
echo " Iniciar Wrapper LXC para Auto-UGC Pipeline"
echo "============================================="

# 1. Crear el contenedor
if lxc info "$CONTAINER_NAME" >/dev/null 2>&1; then
    echo "[!] El contenedor '$CONTAINER_NAME' ya existe. Omitiendo creación."
else
    echo "[+] Creando contenedor LXC '$CONTAINER_NAME' usando la imagen $IMAGE..."
    lxc launch "$IMAGE" "$CONTAINER_NAME"
fi

# 2. Configurar límites (según mejor juicio / README)
echo "[+] Configurando límites: RAM=$MEMORY_LIMIT, CPU=$CPU_LIMIT..."
lxc config set "$CONTAINER_NAME" limits.memory "$MEMORY_LIMIT"
lxc config set "$CONTAINER_NAME" limits.cpu "$CPU_LIMIT"

# 3. Esperar que el contenedor levante red
echo "[+] Esperando conectividad de red en el contenedor..."
sleep 5

# 4. Instalar dependencias del sistema recomendadas
echo "[+] Instalando prerequisitos (Python, FFmpeg, Git, etc)..."
lxc exec "$CONTAINER_NAME" -- apt-get update
lxc exec "$CONTAINER_NAME" -- apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    ffmpeg libgl1 git curl

# 5. Pasar los archivos del proyecto al contenedor
echo "[+] Transfiriendo archivos del proyecto al contenedor..."
lxc exec "$CONTAINER_NAME" -- mkdir -p /opt/auto-ugc
# Aseguramos que empujamos la carpeta con los archivos a /opt/auto-ugc
lxc file push -p -r "./$PROJECT_DIR/" "$CONTAINER_NAME/opt/auto-ugc/"

# 6. Configurar el entorno virtual e instalar dependencias de Python
echo "[+] Configurando venv local e instalando requirements.txt..."
lxc exec "$CONTAINER_NAME" -- bash -c "
cd /opt/auto-ugc/$PROJECT_DIR/ && \
python3.11 -m venv venv && \
source venv/bin/activate && \
pip install --upgrade pip && \
pip install -r requirements.txt
"

echo "============================================="
echo "¡Entorno LXC configurado exitosamente!"
echo " "
echo "Para acceder al entorno interactivo: "
echo "  lxc exec $CONTAINER_NAME -- bash"
echo " "
echo "Antes de ejecutar, recuerda copiar tus APIs de .env.example:"
echo "  lxc exec $CONTAINER_NAME -- bash -c 'cp /opt/auto-ugc/$PROJECT_DIR/.env.example /opt/auto-ugc/$PROJECT_DIR/.env'"
echo " "
echo "Para arrancar el dashboard web dentro de LXC:"
echo "  lxc exec $CONTAINER_NAME -- bash -c 'cd /opt/auto-ugc/$PROJECT_DIR/ && source venv/bin/activate && python main.py --web'"
echo "============================================="
