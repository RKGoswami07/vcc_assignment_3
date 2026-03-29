import psutil
import subprocess
import time
import tempfile
import os

# Configuration parameters
GCP_PROJECT = "vcc-assignment-3"
GCP_ZONE = "asia-south1-a"
VM_NAME = "vm-autoscaling-raju"
VM_TYPE = "e2-micro"
OS_IMAGE_FAMILY = "ubuntu-2204-lts"
OS_IMAGE_PROJECT = "ubuntu-os-cloud"

USAGE_LIMIT = 75.0
POLL_DELAY = 30  # seconds

def fetch_system_metrics():
    cpu_usage = psutil.cpu_percent(interval=2)
    memory_usage = psutil.virtual_memory().percent
    return cpu_usage, memory_usage


def check_vm_presence():
    response = subprocess.run(
        [
            "gcloud", "compute", "instances", "describe", VM_NAME,
            "--zone", GCP_ZONE,
            "--project", GCP_PROJECT
        ],
        capture_output=True
    )
    return response.returncode == 0


def launch_vm_instance():
    print(f"[WARNING] Resource usage exceeded {USAGE_LIMIT}%. Initiating scale-out...")

    init_script = """#!/bin/bash
cat << 'EOF' > /home/server.py
from http.server import BaseHTTPRequestHandler, HTTPServer

class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<h1>Auto-Scaled GCP Instance Active!</h1><br><h2>VCC Assignment 3 completed successfully</h2>")

    def log_message(self, format, *args):
        pass

app_server = HTTPServer(('0.0.0.0', 8086), WebHandler)
app_server.serve_forever()
EOF
python3 /home/server.py &
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
        temp_file.write(init_script)
        script_path = temp_file.name

    subprocess.run([
        "gcloud", "compute", "instances", "create", VM_NAME,
        "--project", GCP_PROJECT,
        "--zone", GCP_ZONE,
        "--machine-type", VM_TYPE,
        "--image-family", OS_IMAGE_FAMILY,
        "--image-project", OS_IMAGE_PROJECT,
        "--tags", "http-server",
        "--no-service-account",
        "--no-scopes",
        "--metadata-from-file", f"startup-script={script_path}"
    ])

    os.remove(script_path)

    ip_result = subprocess.run([
        "gcloud", "compute", "instances", "describe", VM_NAME,
        "--zone", GCP_ZONE,
        "--project", GCP_PROJECT,
        "--format=get(networkInterfaces[0].accessConfigs[0].natIP)"
    ], capture_output=True, text=True)

    vm_ip = ip_result.stdout.strip()
    print(f"[INFO] VM '{VM_NAME}' successfully launched.")
    print(f"[INFO] Access the service at: http://{vm_ip}:8086")


def terminate_vm_instance():
    print(f"[INFO] Usage dropped below {USAGE_LIMIT}%. Scaling in (terminating VM)...")

    subprocess.run([
        "gcloud", "compute", "instances", "delete", VM_NAME,
        "--zone", GCP_ZONE,
        "--project", GCP_PROJECT,
        "--quiet"
    ])

    print(f"[INFO] VM '{VM_NAME}' has been terminated.")


if __name__ == "__main__":
    print("Auto-scaling service started...")

    while True:
        cpu_val, mem_val = fetch_system_metrics()
        print(f"CPU Usage: {cpu_val}% | Memory Usage: {mem_val}%")

        vm_active = check_vm_presence()

        if (cpu_val > USAGE_LIMIT or mem_val > USAGE_LIMIT) and not vm_active:
            launch_vm_instance()

        elif cpu_val < USAGE_LIMIT and mem_val < USAGE_LIMIT and vm_active:
            terminate_vm_instance()

        else:
            if vm_active:
                print("[STATUS] High usage detected but VM already running. No action taken.")
            else:
                print("[STATUS] System within limits. No scaling required.")

        time.sleep(POLL_DELAY)