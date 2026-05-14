import sys
import json

# Read input from Node-RED (passed via stdin)
data = sys.stdin.read().strip()

# Your logic here
result = {"input": data, "status": "ok"}

print(json.dumps(result))
