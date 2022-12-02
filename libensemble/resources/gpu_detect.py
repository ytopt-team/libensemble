import os
import ast
import subprocess

# SH TODO - Remove prints


def pynvml():
    """Detect GPU from pynvml or return None"""
    try:
        import pynvml

        pynvml.nvmlInit()
        gpu_count = pynvml.nvmlDeviceGetCount()
        pynvml.nvmlShutdown()
        print("gpu count from pynvml", gpu_count)
    except Exception:
        print("pynvml (optional) not found or failed")
        return None
    return gpu_count


def nvidia_smi():
    """Detect GPU from nvidia-smi or return None"""
    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"])
        gpu_count = len(output.decode().split())
        print("gpu count from nvidia-smi", gpu_count)
    except Exception:
        print("nvidia-smi (optional) not found or failed")
        return None
    return gpu_count


def pyadl():
    """Detect GPU from pyadl or return None"""
    try:
        from pyadl import ADLManager

        devices = ADLManager.getInstance().getDevices()
        gpu_count = len(devices)
        print("gpu count from pyadl", gpu_count)
    except Exception:
        print("pyadl (optional) not found or failed")
        return None
    return gpu_count


def rocm_smi():
    """Detect GPU from rocm-smi or return None"""
    try:
        output = subprocess.check_output(["rocm-smi", "-i", "--json"])
        gpu_count = len(ast.literal_eval(output.decode()))
        print("gpu count from rocm-smi", gpu_count)
    except Exception:
        print("rocm-smi (optional) not found or failed")
        return None
    return gpu_count


METHODS = {
    "pynvml": pynvml,
    "nvidia_smi": nvidia_smi,
    "pyadl": pyadl,
    "rocm_smi": rocm_smi,
}


def get_num_gpus(testall=False):
    """Return number of GPUs on node if can detect - else None"""

    # Default zero or None
    gpu_count = None

    for method in METHODS:
        gpu_count = METHODS[method]()
        if isinstance(gpu_count, int) and not testall:
            return gpu_count

    # gpus not found
    # Simpler for string conversion to return int.
    return 0
    # return None


def get_gpus_from_env(env_resources=None):
    """Returns gpus per node by querying environment or None"""

    if not env_resources:
        return None

    if env_resources.scheduler == "Slurm":
        gpu_count = os.getenv("SLURM_GPUS_ON_NODE")
        print("gpu count from SLURM_GPUS_ON_NODE", gpu_count)
        # return os.getenv("SLURM_GPUS_ON_NODE")
        return gpu_count

    return None

# temp
if __name__ == "__main__":
    get_num_gpus(testall=True)
