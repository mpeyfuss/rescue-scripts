import subprocess


def build_calldata(function_signature: str, args: list[any]) -> str:
    """
    Uses `cast calldata` to build calldata needed for the tx
    """
    cmd = ["cast", "calldata", function_signature, *map(str, args)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()
