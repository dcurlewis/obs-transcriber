import obsws_python as obs
import sys
from config import get_config

def main():
    if len(sys.argv) < 2:
        print("Usage: python obs_controller.py <start|stop>")
        sys.exit(1)

    command = sys.argv[1]
    config = get_config()  # Validates on first call

    try:
        client = obs.ReqClient(host=config.obs_host, port=config.obs_port, password=config.obs_password)
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