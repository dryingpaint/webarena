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
parser.add_argument("--agent", 
                    type=str, 
                    required=True,
                    )
parser.add_argument("--start_port",
                    type=int, 
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

def run_background_server(port):
    actual_port = args.start_port + int(port)
    clear_port(actual_port)
    
    cmd = f"cd ~/altera/lyfe-agent && bazel-bin/main --agents={args.agent} --port {actual_port}"
    logging.info(f"Starting background server: {cmd}")
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
    
    log_file = f"run_outputs/{args.dir}/background_server_{port}.log"
    threading.Thread(target=log_output, args=(process, log_file, f"BG Server {port}"), daemon=True).start()
    
    return process

def run_task(port):
    logging.info(f"Starting task for port {port}")
    
    try:
        server_process = run_background_server(port)
        
        time.sleep(5)  # Adjust as needed
        
        cmd = f"""
        cd ~/webarena
        python -u run.py --dir {args.dir} --agent_type altera --instruction_path agent/prompts/jsons/altera.json --port {args.start_port + int(port)} --test_start_idx {port} --test_end_idx {int(port) + 1}
        """
        
        logging.info(f"Executing command for port {port}")
        
        out_file = f"run_outputs/{args.dir}/out_{port}.txt"
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

def worker(task_type, port):
    return run_task(port)

def terminate_server(server_process):
    if server_process:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        logging.info(f"Terminated background server process")

# def run_docker_commands():
    # commands = [
    #     "docker stop shopping_admin forum gitlab shopping",
    #     "docker rm shopping_admin forum gitlab shopping",
    #     "docker run --name shopping -p 7770:80 -d shopping_final_0712",
    #     "docker run --name shopping_admin -p 7780:80 -d shopping_admin_final_0719",
    #     "docker run --name gitlab -d -p 8023:8023 gitlab-populated-final-port8023 /opt/gitlab/embedded/bin/runsvdir-start",
    #     "docker run --name forum -p 9999:80 -d postmill-populated-exposed-withimg",
    #     "docker start gitlab",
    #     "docker start shopping",
    #     "docker start shopping_admin",
    #     "docker start forum",
    #     "docker start kiwix33",
    #     "cd /home/ubuntu/openstreetmap-website/ && docker compose start",
    #     'docker exec shopping /var/www/magento2/bin/magento setup:store-config:set --base-url="http://${HOSTNAME}:7770"',
    #     'docker exec shopping mysql -u magentouser -pMyPassword magentodb -e \'UPDATE core_config_data SET value="http://${HOSTNAME}:7770/" WHERE path = "web/secure/base_url";\'',
    #     "docker exec shopping_admin php /var/www/magento2/bin/magento config:set admin/security/password_is_forced 0",
    #     "docker exec shopping_admin php /var/www/magento2/bin/magento config:set admin/security/password_lifetime 0",
    #     "docker exec shopping /var/www/magento2/bin/magento cache:flush",
    #     'docker exec shopping_admin /var/www/magento2/bin/magento setup:store-config:set --base-url="http://${HOSTNAME}:7780"',
    #     'docker exec shopping_admin mysql -u magentouser -pMyPassword magentodb -e \'UPDATE core_config_data SET value="http://${HOSTNAME}:7780/" WHERE path = "web/secure/base_url";\'',
    #     "docker exec shopping_admin /var/www/magento2/bin/magento cache:flush",
    #     'docker exec gitlab sed -i "s|^external_url.*|external_url \'http://${HOSTNAME}:8023\'|" /etc/gitlab/gitlab.rb',
    #     "docker exec gitlab gitlab-ctl reconfigure"
    #     "mkdir -p ./.auth",
    #     "python browser_env/auto_login.py",
    # ]
    
    # for cmd in commands:
    #     try:
    #         subprocess.run(cmd, shell=True, check=True)
    #         logging.info(f"Successfully executed: {cmd}")
    #     except subprocess.CalledProcessError as e:
    #         logging.error(f"Error executing command: {cmd}")
    #         logging.error(f"Error details: {str(e)}")

if __name__ == '__main__':
    os.makedirs(f"run_outputs/{args.dir}", exist_ok=True)

    all_tasks = {task_type.value: [] for task_type in TaskType}
    for task_type in TaskType:
        site_tasks = [int(file.replace('.json','')) for file in files_by_task[task_type.value]]
        all_tasks[task_type.value] = sorted(site_tasks)

    logging.info(f"Starting execution with up to 6 parallel tasks, one for each task type")

    batch_count = 0

    while any(tasks for tasks in all_tasks.values()):
        batch_count += 1
        
        # if batch_count % 5 == 1:  # Run Docker commands at the start of every 5th batch
        #     logging.info("Running Docker commands before starting the batch")
        #     run_docker_commands()

        threads = []
        server_processes = []
        for task_type, tasks in all_tasks.items():
            if tasks:
                port = tasks.pop(0)
                t = threading.Thread(target=worker, args=(task_type, port))
                t.start()
                threads.append(t)

        # Wait for all threads in this batch to finish
        for t in threads:
            server_process = t.join()
            if server_process:
                server_processes.append(server_process)

        logging.info(f"Completed batch {batch_count} of tasks")

        # Terminate all background servers for this batch
        for server_process in server_processes:
            terminate_server(server_process)

        logging.info(f"Terminated all background servers for batch {batch_count}")

    logging.info("All tasks completed")