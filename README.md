# Nexus Core - Nomada Inmortal

Base operativa para orquestacion multi-cloud con respaldo continuo:

- Capa de datos persistentes: GitHub + HuggingFace + Supabase + (opcional) rclone/Drive
- Capa de compute nomada: Codespaces, Gitpod, GCP, Oracle, Cloud Shell, HF Space fallback
- Capa de resiliencia: backup/restore + lock distribuido + migracion con verificacion

## Scripts principales

- `scripts/nomad_controller.py`
  - Evalua proveedores por prioridad/quotas.
  - Decide migracion cada ciclo (default 30 min).
  - Ejecuta `auto_backup -> migrate_command -> auto_restore -> verify_command`.
- `scripts/auto_backup.py`
  - Backup a Git.
  - Sync opcional a HuggingFace dataset.
  - Marker opcional en Supabase.
  - Sync opcional a rclone.
- `scripts/auto_restore.py`
  - Restore de Git (fetch/checkout/pull --ff-only).
  - Restore de HuggingFace.
  - Check de conectividad Supabase.
- `scripts/state_manager.py`
  - Lock distribuido (`nexus_locks`) por `task_id`.
  - Heartbeat/release.
  - Insercion a DLQ (`dead_letter_queue`) para fallos.
- `scripts/oracle_sniper.py`
  - Intento OCI cada 15 min (solo `oci-cli`).
  - Ignora capacidad agotada sin ruido.
  - Notifica por webhook cuando detecta `PROVISIONING/RUNNING`.

## Setup rapido

1. Copiar `.env.template` a `.env` y completar secretos.
2. Copiar `configs/nomad_config.example.json` a `configs/nomad_config.json`.
3. Si usaras Oracle CLI: copiar `configs/oracle_launch.example.json` a `configs/oracle_launch.json`.
4. Ajustar `migrate_command` y `verify_command` por proveedor.
5. Instalar dependencias:

```bash
python -m pip install -r requirements.txt
```

## Ejecucion

Dry-run de restore:

```bash
python scripts/auto_restore.py --dry-run
```

Un ciclo de backup:

```bash
python scripts/auto_backup.py --once
```

Un ciclo de orquestacion nomada:

```bash
python scripts/nomad_controller.py --once --dry-run
```

Loop continuo nomada:

```bash
python scripts/nomad_controller.py
```

Lock distribuido:

```bash
python scripts/state_manager.py --action acquire --task-id chapter_01
python scripts/state_manager.py --action heartbeat --task-id chapter_01
python scripts/state_manager.py --action release --task-id chapter_01
```

Oracle sniper:

```bash
python scripts/oracle_sniper.py --once --dry-run
```

## Seguridad de tokens

- No uses PAT en URLs de `git remote`.
- Usa `GH_TOKEN` en entorno de sesion para comandos `gh`.
- Mantener `.env` fuera de git (ya excluido en `.gitignore`).
