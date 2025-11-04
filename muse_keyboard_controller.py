"""
Muse Headband Keyboard Controller

Good games to play:
https://freeinvaders.org/    
https://freeasteroids.org/
"""

import argparse
import sys
import time
from pythonosc import dispatcher as dsp
from pythonosc import osc_server
from pynput.keyboard import Controller, Key, Listener

# Initialize keyboard controller for system-wide events
keyboard = Controller()

# Global flag to track if we've received any OSC data
osc_connected = False

# Track which keys are currently held down for swivel control
left_key_held = False
right_key_held = False

# ==================== CONFIGURATION ====================
# Control mode - Change this to set your preferred mode
# Options: "tilt", "swivel", "both"
CONTROL_MODE = "tilt"  # SET YOUR PREFERRED CONTROL MODE HERE

# Thresholds for detecting head movements
TILT_THRESHOLD = 0.05   # For forward/back and left/right tilt detection
SWIVEL_THRESHOLD = 100  # For yaw (swivel) detection
SWIVEL_RELEASE_THRESHOLD = 50  # Threshold to release held keys

# Calibration settings
CALIBRATION_SAMPLES = 30  # Number of samples to average for calibration
# =======================================================

# Calibration baseline values (set during calibration)
calibrated = False
baseline_acc_x = 0.0 
baseline_acc_y = 0.0
baseline_gyro_z = 0.0
calibration_data = {"acc_x": [], "acc_y": [], "gyro_z": []}

def connection_monitor(unused_addr, *args):
    """Monitors any incoming OSC message to verify connection"""
    global osc_connected
    if not osc_connected:
        print("OSC Connected! Receiving data from Muse headband.")
        osc_connected = True

def calibration_acc_handler(unused_addr, args, x, y, z):
    """Collects accelerometer data for calibration"""
    global calibration_data, calibrated, baseline_acc_x, baseline_acc_y

    if not calibrated and len(calibration_data["acc_x"]) < CALIBRATION_SAMPLES:
        calibration_data["acc_x"].append(x)
        calibration_data["acc_y"].append(y)

        # Calculate and set baseline when we have enough samples
        if len(calibration_data["acc_x"]) == CALIBRATION_SAMPLES:
            baseline_acc_x = sum(calibration_data["acc_x"]) / CALIBRATION_SAMPLES
            baseline_acc_y = sum(calibration_data["acc_y"]) / CALIBRATION_SAMPLES
            print(f"Accelerometer calibrated: X={baseline_acc_x:.3f}, Y={baseline_acc_y:.3f}")

            # Mark as fully calibrated when both sensors are done
            if len(calibration_data["gyro_z"]) == CALIBRATION_SAMPLES:
                calibrated = True
                print("\n✓ Calibration complete! Controls are now active.\n")

def calibration_gyro_handler(unused_addr, args, x, y, z):
    """Collects gyroscope data for calibration"""
    global calibration_data, calibrated, baseline_gyro_z

    if not calibrated and len(calibration_data["gyro_z"]) < CALIBRATION_SAMPLES:
        calibration_data["gyro_z"].append(z)

        # Calculate and set baseline when we have enough samples
        if len(calibration_data["gyro_z"]) == CALIBRATION_SAMPLES:
            baseline_gyro_z = sum(calibration_data["gyro_z"]) / CALIBRATION_SAMPLES
            print(f"Gyroscope calibrated: Z={baseline_gyro_z:.3f}")

            # Mark as fully calibrated when both sensors are done
            if len(calibration_data["acc_x"]) == CALIBRATION_SAMPLES :
                calibrated = True
                print("\n✓  plete! Controls are now active.\n")

def debug_handler(addr, *args):
    """Debug: print blink and jaw clench messages"""
    if "blink" in addr.lower() or "jaw" in addr.lower():
        print(f"DEBUG: {addr} -> {args}")

def blink_handler(unused_addr, args, blink):
    """Handles blink events by sending system-wide spacebar key press"""
    if blink:
        print("Blink detected - sending SPACEBAR")
        keyboard.press(Key.space)
        time.sleep(0.1)  # Short delay to ensure key press is registered
        keyboard.release(Key.space)

def jaw_clench_handler(unused_addr, args, jaw_clench):
    """Handles jaw clench events by sending system-wide up arrow key press"""
    if jaw_clench:
        print("Jaw clench detected - sending UP arrow key")
        keyboard.press(Key.up)
        keyboard.release(Key.up)

def accelerometer_handler(unused_addr, args, x, y, z):
    """
    Handles accelerometer data for head tilt detection
    x: forward/back tilt (positive = forward, negative = back)
    y: left/right tilt (positive = right, negative = left)
    z: up/down (gravity reference)
    """
    # Skip if tilt controls are disabled
    if CONTROL_MODE == "swivel":
        return

    # Skip if not calibrated yet
    if not calibrated:
        return

    # Calculate relative tilt from baseline (calibrated center)
    rel_x = x - baseline_acc_x
    rel_y = y - baseline_acc_y

    # # Forward tilt - send UP arrow
    # if rel_x > TILT_THRESHOLD:
    #     print(f"Tilt FORWARD detected (rel_x={rel_x:.2f}) - sending UP arrow")
    #     keyboard.press(Key.up)

    # # Backward tilt - send DOWN arrow
    # elif rel_x < -TILT_THRESHOLD:
    #     print(f"Tilt BACK detected (rel_x={rel_x:.2f}) - sending DOWN arrow")
    #     keyboard.press(Key.down)
    
    # # Release UP/DOWN keys if within threshold
    # else:
    #     keyboard.release(Key.up)
    #     keyboard.release(Key.down)

    # Left tilt - send LEFT arrow
    if rel_y < -TILT_THRESHOLD:
        print(f"Tilt LEFT detected (rel_y={rel_y:.2f}) - sending LEFT arrow")
        keyboard.press(Key.left)

    # Right tilt - send RIGHT arrow
    elif rel_y > TILT_THRESHOLD:
        print(f"Tilt RIGHT detected (rel_y={rel_y:.2f}) - sending RIGHT arrow")
        keyboard.press(Key.right)
    
    # Release LEFT/RIGHT keys if within threshold
    else:
        keyboard.release(Key.left)
        keyboard.release(Key.right)

def gyroscope_handler(unused_addr, args, x, y, z):
    """
    Handles gyroscope data for head swivel (yaw) detection
    z: yaw/swivel (positive = turning right, negative = turning left)
    Keys are HELD DOWN until head returns to center
    """
    global left_key_held, right_key_held

    # Skip if swivel controls are disabled
    if CONTROL_MODE == "tilt":
        return

    # Skip if not calibrated yet
    if not calibrated:
        return

    # Calculate relative rotation from baseline (calibrated center)
    rel_z = z - baseline_gyro_z

    # Swivel LEFT - hold LEFT arrow
    if rel_z < -SWIVEL_THRESHOLD:
        if not left_key_held:
            print(f"Swivel LEFT detected (rel_z={rel_z:.2f}) - HOLDING LEFT arrow")
            keyboard.press(Key.left)
            left_key_held = True
        # Release right key if it was held
        if right_key_held:
            keyboard.release(Key.right)
            right_key_held = False

    # Swivel RIGHT - hold RIGHT arrow
    elif rel_z > SWIVEL_THRESHOLD:
        if not right_key_held:
            print(f"Swivel RIGHT detected (rel_z={rel_z:.2f}) - HOLDING RIGHT arrow")
            keyboard.press(Key.right)
            right_key_held = True
        # Release left key if it was held
        if left_key_held:
            keyboard.release(Key.left)
            left_key_held = False

    # Center position - release both keys
    elif abs(rel_z) < SWIVEL_RELEASE_THRESHOLD:
        if left_key_held:
            print(f"Swivel CENTER detected (rel_z={rel_z:.2f}) - releasing LEFT arrow")
            keyboard.release(Key.left)
            left_key_held = False
        if right_key_held:
            print(f"Swivel CENTER detected (rel_z={rel_z:.2f}) - releasing RIGHT arrow")
            keyboard.release(Key.right)
            right_key_held = False

def on_key_press(key):
    """Handle keyboard input - stop program on ESC"""
    try:
        if key == Key.esc:
            print("\n\nESC pressed - shutting down...")
            sys.exit(0)
    except:
        pass

def start_osc(ip, port):
    """Start OSC server to listen for Muse headband events"""
    dispatcher = dsp.Dispatcher()

    # Add connection monitor for any Muse message
    dispatcher.map("/muse/*", connection_monitor)

    # Debug: catch all messages to see what's being sent
    dispatcher.map("/*", debug_handler)

    # Specific handler for blinks
    dispatcher.map("/muse/elements/blink", blink_handler, "EEG")

    # Specific handler for jaw clenches
    dispatcher.map("/muse/elements/jaw_clench", jaw_clench_handler, "EEG")

    # Handlers for head movements (with calibration)
    dispatcher.map("/muse/acc", calibration_acc_handler, "ACC")
    dispatcher.map("/muse/acc", accelerometer_handler, "ACC")
    dispatcher.map("/muse/gyro", calibration_gyro_handler, "GYRO")
    dispatcher.map("/muse/gyro", gyroscope_handler, "GYRO")

    server = osc_server.ThreadingOSCUDPServer(
        (ip, port), dispatcher)
    print(f"Serving on {server.server_address}")
    print("Waiting for OSC connection from Muse headband...")

    print("\n" + "=" * 60)
    print("CALIBRATION")
    print("=" * 60)
    print("When the headband connects, hold your head in a")
    print("comfortable NEUTRAL position for a few seconds.")
    print("This position will be set as your 'center'.")
    print("=" * 60)

    print("\nControls:")
    print("  - Blink: SPACEBAR")
    print("  - Jaw Clench: UP arrow key")

    # Show active controls based on mode
    if CONTROL_MODE in ["tilt", "both"]:
        print("\nTilt Controls (active):")
        print("  - Tilt Forward: UP arrow key")
        print("  - Tilt Back: DOWN arrow key")
        print("  - Tilt Left: LEFT arrow key")
        print("  - Tilt Right: RIGHT arrow key")

    if CONTROL_MODE in ["swivel", "both"]:
        print("\nSwivel Controls (active):")
        print("  - Swivel Left: HOLD LEFT arrow key")
        print("  - Swivel Right: HOLD RIGHT arrow key")

    if CONTROL_MODE == "tilt":
        print("\n(Swivel controls disabled)")
    elif CONTROL_MODE == "swivel":
        print("\n(Tilt controls disabled)")

    print("\nPress ESC or Ctrl+C to exit")
    server.serve_forever()

def main():
    global CONTROL_MODE

    parser = argparse.ArgumentParser(description="Muse Headband Keyboard Controller")
    parser.add_argument("--ip",
                        default="10.37.194.91",
                        help="The IP address to listen on")
    parser.add_argument("--port",
                        type=int,
                        default=5000,
                        help="The port to listen on")
    parser.add_argument("--mode",
                        choices=["tilt", "swivel", "both"],
                        default=None,
                        help="Control mode: 'tilt' for tilt controls only, 'swivel' for swivel controls only, 'both' for all controls (overrides CONTROL_MODE setting)")
    args = parser.parse_args()

    # Override CONTROL_MODE if --mode argument is provided
    if args.mode is not None:
        CONTROL_MODE = args.mode

    print("=" * 60)
    print("Muse Headband Keyboard Controller")
    print("=" * 60)
    print("This program will generate SYSTEM-WIDE keyboard events")
    print(f"Control mode: {CONTROL_MODE.upper()}")
    print("=" * 60)

    # Start keyboard listener for ESC key in background
    listener = Listener(on_press=on_key_press)
    listener.start()

    try:
        start_osc(args.ip, args.port)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        listener.stop()

if __name__ == '__main__':
    main()
