import os

base_url = os.getenv("BASE_URL", "https://lab.care.ai")
lab_scope = os.getenv("LAB_SCOPE", "lab-auth-db")
# number of seconds to wait when explicit waits are needed
try:
    timeout = int(os.getenv("TIMEOUT", "10"))
except ValueError:
    timeout = 10

# browser configuration
browser = os.getenv("BROWSER", "edge")  # Options: chrome, firefox, edge, safari
headless = os.getenv("HEADLESS", "False").lower() in ("true", "1", "yes")  # run in headless mode if set

# IDA-5376 virtual monitoring auth-resilience tests
ida5376_observe_seconds = int(os.getenv("IDA5376_OBSERVE_SECONDS", "90"))
ida5376_recovery_wait_seconds = int(os.getenv("IDA5376_RECOVERY_WAIT_SECONDS", "60"))
ida5376_facility = os.getenv("IDA5376_FACILITY", "Vineland Rack Room")
ida5376_min_rooms = int(os.getenv("IDA5376_MIN_ROOMS", "2"))
ida5376_vm_path = os.getenv("IDA5376_VM_PATH", "/virtual-monitoring")
ida5376_beta_vm_path = os.getenv("IDA5376_BETA_VM_PATH", "")