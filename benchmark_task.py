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


hostname = 'ec2-3-145-147-254.us-east-2.compute.amazonaws.com'
os.environ['HOSTNAME'] = hostname

os.environ['SHOPPING'] = f"http://{hostname}:7770"
os.environ['SHOPPING_ADMIN'] = f"http://{hostname}:7780/admin"
os.environ['REDDIT'] = f"http://{hostname}:9999"
os.environ['GITLAB'] = f"http://{hostname}:8023"
os.environ['MAP'] = f"http://{hostname}:3000"
os.environ['WIKIPEDIA'] = f"http://{hostname}:8888"
os.environ['HOMEPAGE'] = f"http://{hostname}:4399"

class TaskType(Enum):
    # SHOPPING = 'shopping'
    REDDIT = 'reddit'
    WIKI = 'wikipedia'
    MAP = 'map'
    GITLAB = 'gitlab'
    SHOPPING_ADMIN = 'shopping_admin'

files_by_task = {task.value: [] for task in TaskType}

parser = argparse.ArgumentParser()
parser.add_argument("--dir", 
                    type=str, 
                    required=True,
                    )
args = parser.parse_args()

dir = args.dir

files = os.listdir('config_files')
for file in files:
    path = f'config_files/{file}'
    if os.path.isdir(path) or 'test' in path:
        continue
    with open(path) as f:
        config = json.load(f)
        for site in config['sites']:
            if site == 'shopping':
                continue
            files_by_task[site].append(file)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def run_background_server(port, task_type):
    actual_port = 8100 + int(port)
    clear_port(actual_port)
    
    cmd = f"cd ~/altera/lyfe-agent && bazel-bin/main --agents=webb --port {actual_port}"
    logging.info(f"Starting background server: {cmd}")
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
    
    log_file = f"run_outputs/{task_type}/background_server_{port}.log"
    threading.Thread(target=log_output, args=(process, log_file, f"BG Server {port}"), daemon=True).start()
    
    return process

def run_task(port, task_type):
    logging.info(f"Starting task for port {port}")
    
    try:
        server_process = run_background_server(port, task_type)
        
        time.sleep(5)  # Adjust as needed
        
        cmd = f"""
        cd ~/webarena
        python -u run.py --dir {task_type} --agent_type altera --instruction_path agent/prompts/jsons/altera.json --port {8100 + int(port)} --test_start_idx {port} --test_end_idx {int(port) + 1}
        """
        
        logging.info(f"Executing command for port {port}")
        
        out_file = f"run_outputs/{task_type}/out_{port}.txt"
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
        
        return server_process
    
    except Exception as e:
        logging.error(f"Unexpected error for port {port}: {str(e)}")
        return None

def worker(task_queue, result_queue):
    while True:
        task = task_queue.get()
        if task is None:
            break
        task_type, port = task
        server_process = run_task(port, task_type)
        result_queue.put(server_process)

if __name__ == '__main__':
    for task_type in TaskType:
        os.makedirs(f"run_outputs/{task_type.value}", exist_ok=True)

    all_tasks = []
    for task_type in TaskType:
        site_tasks = [int(file.replace('.json','')) for file in files_by_task[task_type.value]]
        site_tasks = sorted(site_tasks)
        all_tasks.extend((task_type.value, port) for port in site_tasks)

    logging.info(f"Starting execution with 6 parallel tasks, one for each task type")

    task_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()

    for task in all_tasks:
        task_queue.put(task)

    num_workers = min(6, len(all_tasks))
    workers = []
    for _ in range(num_workers):
        worker_process = multiprocessing.Process(target=worker, args=(task_queue, result_queue))
        worker_process.start()
        workers.append(worker_process)

    batch_size = 6
    batch_processes = []

    while not task_queue.empty() or any(worker.is_alive() for worker in workers):
        while len(batch_processes) < batch_size and not result_queue.empty():
            process = result_queue.get()
            if process:
                batch_processes.append(process)

        if len(batch_processes) == batch_size or (task_queue.empty() and not result_queue.empty()):
            # Terminate all processes in the current batch
            for process in batch_processes:
                process.terminate()
                process.wait()
            batch_processes.clear()

        time.sleep(1)  # Avoid busy waiting

    # Signal workers to stop
    for _ in workers:
        task_queue.put(None)

    # Wait for all worker processes to finish
    for worker_process in workers:
        worker_process.join()

    logging.info("All tasks completed")