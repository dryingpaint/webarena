import subprocess
import multiprocessing
import os
import argparse
from enum import Enum
import json
import logging
import time
import sys
import threading
import csv
import math

hostname = 'ec2-13-59-52-33.us-east-2.compute.amazonaws.com'
os.environ['HOSTNAME'] = hostname

os.environ['SHOPPING'] = f"http://{hostname}:7770"
os.environ['SHOPPING_ADMIN'] = f"http://{hostname}:7780/admin"
os.environ['REDDIT'] = f"http://{hostname}:9999"
os.environ['GITLAB'] = f"http://{hostname}:8023"
os.environ['MAP'] = f"http://{hostname}:3000"
os.environ['WIKIPEDIA'] = f"http://{hostname}:8888"
os.environ['HOMEPAGE'] = f"http://{hostname}:4399"

class TaskType(Enum):
    SHOPPING = 'shopping'
    REDDIT = 'reddit'
    WIKI = 'wikipedia'
    MAP = 'map'
    GITLAB = 'gitlab'
    SHOPPING_ADMIN = 'shopping_admin'

files_by_task = {task.value: [] for task in TaskType}

parser = argparse.ArgumentParser()
parser.add_argument("--type", 
                    type=str, 
                    required=False,
                    default="shopping", 
                    )
args = parser.parse_args()

files = os.listdir('config_files')
for file in files:
    path = f'config_files/{file}'
    if os.path.isdir(path) or 'test' in path:
        continue
    with open(path) as f:
        config = json.load(f)
        for site in config['sites']:
            files_by_task[site].append(file)

# print(files_by_task)
assert args.type in files_by_task

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
num_cores = multiprocessing.cpu_count()
# Set max_parallel to 1.5 times the number of cores
max_parallel = int(10)

def clear_port(port):
    try:
        cmd = f"lsof -ti:{port}"
        process = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if process.stdout:
            pid = process.stdout.strip()
            kill_cmd = f"kill -9 {pid}"
            subprocess.run(kill_cmd, shell=True, check=True)
            logging.info(f"Cleared process on port {port}")
        else:
            logging.info(f"No process found on port {port}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error clearing port {port}: {e}")

def log_output(process, file_path, prefix):
    with open(file_path, 'w') as f:
        for line in process.stdout:
            f.write(line)
            f.flush()

def run_background_server(port):
    actual_port = 8100 + int(port)
    clear_port(actual_port)
    
    cmd = f"cd ~/altera/lyfe-agent && bazel-bin/main --agents=webb --port {actual_port}"
    logging.info(f"Starting background server: {cmd}")
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
    
    log_file = f"run_outputs/{args.type}/background_server_{port}.log"
    threading.Thread(target=log_output, args=(process, log_file, f"BG Server {port}"), daemon=True).start()
    
    return process

def run_task(port):
    logging.info(f"Starting task for port {port}")
    
    try:
        server_process = run_background_server(port)
        
        time.sleep(5)  # Adjust as needed
        
        cmd = f"""
        cd ~/webarena
        python -u run.py --agent_type altera --instruction_path agent/prompts/jsons/altera.json --port {8100 + int(port)} --test_start_idx {port} --test_end_idx {int(port) + 1}
        """
        
        logging.info(f"Executing command for port {port}")
        
        out_file = f"run_outputs/{args.type}/out_{port}.txt"
        with open(out_file, "w") as f:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, 
                                    stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            for line in proc.stdout:
                f.write(line)
                f.flush()
        
        proc.wait()
        if proc.returncode != 0:
            logging.error(f"Command for port {port} failed with return code {proc.returncode}")
        else:
            logging.info(f"Command for port {port} completed successfully")
        
        server_process.terminate()
        server_process.wait()
    
    except Exception as e:
        logging.error(f"Unexpected error for port {port}: {str(e)}")

def run_batch(batch):
    pool = multiprocessing.Pool(processes=len(batch))
    pool.map(run_task, batch)
    pool.close()
    pool.join()

if __name__ == '__main__':
    site_tasks = [int(file.replace('.json','')) for file in files_by_task[args.type]]
    site_tasks = sorted(site_tasks)
    
    os.makedirs(f"run_outputs/{args.type}", exist_ok=True)
    
    total_tasks = len(site_tasks)
    num_batches = math.ceil(total_tasks / max_parallel)
    
    logging.info(f"Starting execution with {total_tasks} tasks in {num_batches} batches")
    
    for i in range(num_batches):
        start_idx = i * max_parallel
        end_idx = min((i + 1) * max_parallel, total_tasks)
        current_batch = site_tasks[start_idx:end_idx]
        
        logging.info(f"Running batch {i+1}/{num_batches} with {len(current_batch)} tasks")
        run_batch(current_batch)
        logging.info(f"Completed batch {i+1}/{num_batches}")
    
    logging.info("All tasks completed")