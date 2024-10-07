import os
import subprocess
import time
from PIL import ImageGrab
import numpy as np
import cv2

# Parameters
window_name = "IC Simulator"  # Set the name of the window to track
interval_ms = 2  # Interval in milliseconds (e.g., 1000ms = 1 second)
threshold = 0.40  # Percentage of difference to break the loop
log_file_path = "candump-2024-09-30_205136.log"  # Path to the log file
lines_to_keep = 1000  # Number of lines to keep in the final split (to play 100 times)

def get_window_geometry(window_name):
    """ Get the window geometry (position and size) using xdotool. """
    try:
        window_id = subprocess.check_output(["xdotool", "search", "--name", window_name]).decode("utf-8").strip()
        window_info = subprocess.check_output(["xwininfo", "-id", window_id]).decode("utf-8")
        
        x = int(next(line for line in window_info.splitlines() if "Absolute upper-left X" in line).split(":")[1].strip())
        y = int(next(line for line in window_info.splitlines() if "Absolute upper-left Y" in line).split(":")[1].strip())
        width = int(next(line for line in window_info.splitlines() if "Width" in line).split(":")[1].strip())
        height = int(next(line for line in window_info.splitlines() if "Height" in line).split(":")[1].strip())
        
        return (x, y, x + width, y + height)
    except subprocess.CalledProcessError:
        raise Exception(f"Window '{window_name}' not found.")

def get_window_screenshot(window_geometry):
    """ Get a screenshot of the specified window region. """
    screenshot = ImageGrab.grab(window_geometry)
    return screenshot

def compare_images(img1, img2):
    """ Compare two images and return the percentage difference. """
    img1 = np.array(img1)
    img2 = np.array(img2)

    img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    diff = cv2.absdiff(img1_gray, img2_gray)

    non_zero_count = np.count_nonzero(diff)
    total_count = diff.size
    difference_percentage = (non_zero_count / total_count) * 100

    return difference_percentage

def run_command(command):
    """ Run a command in a terminal and return the process. """
    terminal_command = f"sh -c '{command}'"
    process = subprocess.Popen(terminal_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process

def check(command_process):
    print(f"Looking for window: {window_name}")
    
    window_geometry = get_window_geometry(window_name)
    base_image = get_window_screenshot(window_geometry)
    
    print("Starting to monitor changes...")
    
    last_output_time = time.time()  # Initialize the last output time
    output_timeout = 5  # Timeout in seconds for checking command output

    while True:
        retcode = command_process.poll()
        
        output = command_process.stdout.read(1024)
        
        if output:
            last_output_time = time.time()  
        elif time.time() - last_output_time > output_timeout:
            print("No output received from command for a while. Exiting...")
            break
        
        if retcode is not None:  # This indicates the process has ended
            print("The command has finished executing.")
            new_image = get_window_screenshot(window_geometry)
            difference = compare_images(base_image, new_image)
            print(f"Difference: {difference:.2f}%")
            
            if difference > threshold:
                print(f"Breaking the loop. Difference of {difference:.2f}% exceeded the threshold of {threshold}%")
                return True  # Indicate a visual change detected
            break
        
        time.sleep(interval_ms / 1000.0)
        
        new_image = get_window_screenshot(window_geometry)
        difference = compare_images(base_image, new_image)
        print(f"Difference: {difference:.2f}%")
        
        if difference > threshold:
            print(f"Breaking the loop. Difference of {difference:.2f}% exceeded the threshold of {threshold}%")
            return True  # Indicate a visual change detected

    return False  # No visual change detected

def split_and_check(log_file):
    """ Split the log file and check which part activates the screen. """
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    total_lines = len(lines)

    # Base case: If the file has lines_to_keep or fewer, return it
    if total_lines <= lines_to_keep:
        print(f"Final segment with {total_lines} lines: {log_file}")
        return lines  # Return the list of lines for further processing

    # Split the log file in half
    mid_index = total_lines // 2
    first_half = lines[:mid_index]
    second_half = lines[mid_index:]

    # Create temporary files for each half
    first_half_file = "first_half.log"
    second_half_file = "second_half.log"

    with open(first_half_file, 'w') as f:
        f.writelines(first_half)
    
    with open(second_half_file, 'w') as f:
        f.writelines(second_half)
    
    time.sleep(1)

    # Check which half causes a change
    if check(run_command(f"canplayer -I {first_half_file} -g 25 -v")):
        print("First half activated something. Checking further...")
        return split_and_check(first_half_file)  # Recursively check the first half
    elif check(run_command(f"canplayer -I {second_half_file} -g 25 -v")):
        print("Second half activated something. Checking further...")
        return split_and_check(second_half_file)  # Recursively check the second half
    else:
        print("No activation detected in either half.")

def play_lines(lines):
    """ Play each line in the log file 100 times while checking for visual changes. """
    time.sleep(2)
    for line in lines:
        canCommand = line.split()[2]
        command = f"cansend vcan0 {canCommand}"
        print(f"Playing line: {line.strip()} 100 times")

        window_geometry = get_window_geometry(window_name)
        base_image = get_window_screenshot(window_geometry)
        
        for _ in range(50):  # Play each line 100 times
            run_command(command)
            print(command)
            new_image = get_window_screenshot(window_geometry)
            difference = compare_images(base_image, new_image)
            print(f"Difference: {difference:.2f}%")
            
            if difference > threshold:
                print(f"Change detected with line: {line.strip()}")
                return line.strip()
                break  # Stop if a visual change is detected

if __name__ == "__main__":
    final_log_lines = split_and_check(log_file_path)  # Start the splitting and checking process
    if final_log_lines:
        play_lines(final_log_lines)  # Play the lines if any final log lines are returned
