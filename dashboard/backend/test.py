from flask import Flask, jsonify
import os
import sys
import logging

# Disable Flask's default logging to keep the output clean for the master agent
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# Counter to simulate a crash
request_count = 0

@app.route('/')
def home():
    """
    Main endpoint that simulates a crash after a few requests.
    """
    global request_count
    request_count += 1
    
    # After 3 successful requests, this will cause the app to crash
    if request_count > 3:
        print("WORKER ERROR: Simulating a crash due to high request count!", file=sys.stderr)
        # A non-zero exit code indicates an error
        os._exit(1)
        
    return jsonify({
        "message": "This is a test worker application.",
        "status": "ok",
        "request_count": request_count
    })

@app.route('/health')
def health_check():
    """
    A simple health check endpoint that always returns a success status.
    """
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    print("[Test Worker] Starting Flask app on port 9001...")
    # The master agent will monitor this port.
    # The host is set to '0.0.0.0' to be accessible from other services.
    app.run(host='0.0.0.0', port=9001)
