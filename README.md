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
- `scripts/ops_status.ps1`
  - Diagnostico de disco, bridge/hub, python, toolchain y git.
- `scripts/safe_space_recovery.ps1`
  - Recuperacion de espacio segura (caches regenerables, sin cookies/sesiones).
- `scripts/bootstrap_windows_toolchain.ps1`
  - Detecta Python util, guarda `NEXUS_PYTHON` y genera `configs/nomad_config.json` local.

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

## GitHub + Docker (para estabilidad y menos trabas)

Objetivo:
- Guardar estado continuamente en GitHub.
- Ejecutar servicios pesados en contenedores.
- Montar datos en `D:` para no llenar `C:`.

Preparacion en Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docker_prepare.ps1
```

Si Docker no esta instalado:

```powershell
winget install -e --id Docker.DockerDesktop
```

Levantar stack:

```powershell
docker compose -f docker-compose.nexus.yml up -d
```

Detener stack:

```powershell
docker compose -f docker-compose.nexus.yml down
```

Snapshot manual a GitHub:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/github_snapshot.ps1 -Message "checkpoint antes de migracion"
```

Ops status (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ops_status.ps1
```

Recuperar espacio seguro (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/safe_space_recovery.ps1 -TargetFreeGb 2
```

Para forzar OneDrive a "solo en linea" en rutas pesadas:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/safe_space_recovery.ps1 -ForceOneDriveOnlineOnly
```

Bootstrap toolchain (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_windows_toolchain.ps1
```

## Seguridad de tokens

- No uses PAT en URLs de `git remote`.
- Usa `GH_TOKEN` en entorno de sesion para comandos `gh`.
- Mantener `.env` fuera de git (ya excluido en `.gitignore`).
