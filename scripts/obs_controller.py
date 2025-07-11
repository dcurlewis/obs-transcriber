import obsws_python as obs
import sys
import os
from dotenv import load_dotenv

# --- Configuration ---
def get_config():
    """Loads configuration from .env file and falls back to environment variables."""
    # Load .env file from the project root.
    # Assumes script is run from root or from the scripts/ directory.
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
    else:
        # If not found, try loading from current dir (for running from root)
        load_dotenv()

    return {
        "host": os.environ.get('OBS_HOST', 'localhost'),
        "port": int(os.environ.get('OBS_PORT', 4455)),
        "password": os.environ.get('OBS_PASSWORD', 'your_obs_websocket_password')
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python obs_controller.py <start|stop>")
        sys.exit(1)

    command = sys.argv[1]
    config = get_config()

    try:
        client = obs.ReqClient(host=config['host'], port=config['port'], password=config['password'])
    except ConnectionRefusedError:
        print("Error: Connection refused. Is OBS running and the websocket plugin enabled?")
        sys.exit(1)
    except Exception as e:
        print(f"Error connecting to OBS: {e}")
        sys.exit(1)


    if command == "start":
        try:
            # Check if already recording
            resp = client.get_record_status()
            if resp.output_active:
                print("Already recording.")
            else:
                client.start_record()
                print("Started recording.")
        except Exception as e:
            print(f"Error starting recording: {e}")
            sys.exit(1)

    elif command == "stop":
        try:
            # Check if we are recording
            resp = client.get_record_status()
            if not resp.output_active:
                print("Not recording.")
            else:
                client.stop_record()
                print("Stopped recording.")
        except Exception as e:
            print(f"Error stopping recording: {e}")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main() 