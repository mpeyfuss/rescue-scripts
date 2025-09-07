from src.rescue import rescue

# Get input config file
config_fp = input("Please input the path to the config file: ")

# Get extra priority fee
extra_priority_fee = float(
    input("Please input any extra priority fee you want to add (gwei): ")
)

# Rescue
rescue(config_fp, extra_priority_fee)
