#!/usr/bin/env python3
"""Auto-restore: Restaura estado al iniciar en un nuevo entorno."""
import subprocess, os, logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [RESTORE] %(message)s')

def restore():
    nexus_dir = os.environ.get('NEXUS_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    logging.info("Verificando Git...")
    result = subprocess.run(['git', 'status'], cwd=nexus_dir, capture_output=True, text=True)
    if result.returncode == 0:
        subprocess.run(['git', 'pull', 'origin', 'main'], cwd=nexus_dir, capture_output=True)
        logging.info("Git pull OK")
    
    supabase_url = os.environ.get('SUPABASE_URL')
    if supabase_url:
        logging.info(f"Supabase: {supabase_url[:30]}...")
    else:
        logging.warning("SUPABASE_URL no configurado")
    
    hf_token = os.environ.get('HF_TOKEN')
    if hf_token:
        logging.info("Descargando knowledge de HuggingFace...")
        knowledge_dir = os.path.join(nexus_dir, 'knowledge')
        os.makedirs(knowledge_dir, exist_ok=True)
        subprocess.run([
            'huggingface-cli', 'download', 'israel-nexus/knowledge-base',
            '--local-dir', knowledge_dir, '--token', hf_token
        ], capture_output=True)
    
    logging.info("Restore completado.")

if __name__ == '__main__':
    restore()
