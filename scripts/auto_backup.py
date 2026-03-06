#!/usr/bin/env python3
"""Auto-backup: Guarda estado cada 30 minutos a GitHub + HuggingFace."""
import subprocess, os, time, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [BACKUP] %(message)s')
NEXUS_DIR = os.environ.get('NEXUS_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def git_backup():
    try:
        subprocess.run(['git', 'add', '-A'], cwd=NEXUS_DIR, capture_output=True)
        msg = f"auto-backup {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        result = subprocess.run(['git', 'commit', '-m', msg], cwd=NEXUS_DIR, capture_output=True, text=True)
        if 'nothing to commit' not in result.stdout:
            subprocess.run(['git', 'push', 'origin', 'main'], cwd=NEXUS_DIR, capture_output=True)
            logging.info("Git backup completado")
        else:
            logging.info("Sin cambios")
    except Exception as e:
        logging.error(f"Git backup fallo: {e}")

def hf_backup():
    token = os.environ.get('HF_TOKEN')
    if not token:
        return
    try:
        subprocess.run([
            'huggingface-cli', 'upload', 'israel-nexus/knowledge-base',
            os.path.join(NEXUS_DIR, 'knowledge'), '.',
            '--token', token
        ], capture_output=True)
        logging.info("HuggingFace backup completado")
    except Exception as e:
        logging.error(f"HF backup fallo: {e}")

if __name__ == '__main__':
    logging.info("Auto-backup iniciado. Ciclo cada 30 min.")
    while True:
        git_backup()
        hf_backup()
        time.sleep(1800)
