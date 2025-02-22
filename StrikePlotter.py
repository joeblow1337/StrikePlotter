import os
import subprocess
import threading
import time
import datetime
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.stats import linregress
import signal

FETCH_INTERVAL = 60 * 5

DOCKER_COMMAND = [
    "docker", "run", "--rm", "--shm-size=2gb", "--entrypoint=node", "buildkite/puppeteer:latest", "-e",
    "const puppeteer = require('puppeteer');\n"
    "(async () => {\n"
    "    const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });\n"
    "    const page = await browser.newPage();\n"
    "    await page.goto('https://generalstrikeus.com/');\n"
    "    const numbers = await page.evaluate(() => {\n"
    "        return Array.from(document.querySelectorAll('h1'))\n"
    "            .map(h1 => h1.textContent.match(/[0-9]{1,3}([.,][0-9]{3})*([.,][0-9]+)?/g))\n"
    "            .flat()\n"
    "            .filter(Boolean)\n"
    "            .map(n => parseFloat(n.replace(/,/g, '')));\n"
    "    });\n"
    "    if (numbers.length >= 2 && numbers[1] !== 0) {\n"
    "        console.log((numbers[0] / numbers[1] * 100).toFixed(3));\n"
    "    } else {\n"
    "        console.log('NaN');\n"
    "    }\n"
    "    await browser.close();\n"
    "})();"
]

running = True
fetch_interval = FETCH_INTERVAL
next_fetch_time = time.time() + fetch_interval

def signal_handler(sig, frame):
    global running
    running = False
    print("\nStopping logging and plotting...")
    plt.close()
    exit(0)

def fetch_progress():
    try:
        result = subprocess.run(DOCKER_COMMAND, capture_output=True, text=True)
        return result.stdout.strip()
    except Exception:
        return "NaN"

def log_progress():
    global next_fetch_time
    log_file = "progress.log"
    while running:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        progress = fetch_progress()
        with open(log_file, "a") as f:
            f.write(f"{timestamp} - {progress}%\n")
        next_fetch_time = time.time() + fetch_interval
        time.sleep(fetch_interval)

def read_data(filename):
    timestamps, values = [], []
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split(' - ')
            if len(parts) != 2:
                continue
            try:
                timestamp = datetime.datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
                value = float(parts[1].strip('%'))
                timestamps.append(timestamp)
                values.append(value)
            except ValueError:
                continue
    return timestamps, values

def calculate_regression(timestamps, values):
    if len(timestamps) < 2:
        return None, None, None
    x = np.array([t.timestamp() for t in timestamps])
    y = np.array(values)
    slope, intercept, _, _, _ = linregress(x, y)
    if slope <= 0:
        return None, None, None
    target_x = (100 - intercept) / slope
    target_time = datetime.datetime.fromtimestamp(target_x)
    delta_slope = slope * 60
    return target_time, (target_time - datetime.datetime.now()), delta_slope

def live_plot(filename):
    plt.ion()
    fig, ax = plt.subplots()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    ax.set_xlabel("Time")
    ax.set_ylabel("Value (%)")
    ax.set_ylim(0, 100)
    
    while running:
        timestamps, values = read_data(filename)
        ax.clear()
        ax.plot(timestamps, values, marker='o', linestyle='-')
        ax.set_ylim(0, 100)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        fetch_countdown = max(0, int(next_fetch_time - time.time()))
        target_time, countdown, delta_slope = calculate_regression(timestamps, values)

        time_intervals = {
            "1 Minute": 1,
            "1 Hour": 60,
            "1 Day": 60 * 24,
            "1 Week": 60 * 24 * 7
        }
        
        slopes = {}
        slope_texts = []
        for label, interval in time_intervals.items():
            delta_slope = calculate_regression(timestamps, values)[2] * interval
            slopes[label] = delta_slope
            if delta_slope:
                if label == "1 Minute":
                    unit = "minute"
                elif label == "1 Hour":
                    unit = "hour"
                elif label == "1 Day":
                    unit = "day"
                elif label == "1 Week":
                    unit = "week"
                
                slope_texts.append(f"{label}Δ: {delta_slope:.3f}%/{unit}")
            else:
                slope_texts.append(f"{label}Δ: N/A")

        if values:
            current_progress = values[-1]
        else:
            current_progress = "N/A"
        
        title = f"Next fetch in {fetch_countdown} seconds\nCurrent Progress: {current_progress}%\n"
        title += "\n".join(slope_texts)
        if target_time:
            title += f"\nProjected 100% at {target_time}\nTime remaining: {countdown}"

        ax.set_title(title)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.pause(1)

def start_logging():
    thread = threading.Thread(target=log_progress, daemon=True)
    thread.start()

def main():
    signal.signal(signal.SIGINT, signal_handler)
    start_logging()
    live_plot("progress.log")

if __name__ == "__main__":
    main()

