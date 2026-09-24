import logging
import time

import docker

from .base import EVALUATOR_LABEL, EXPIRES_LABEL

logger = logging.getLogger(__name__)

def remove_expired(now=None):
    now = time.time() if now is None else now
    removed = {'containers': 0, 'networks': 0}

    try:
        client = docker.from_env()
        containers = client.containers.list(all=True, filters={'label': f'{EVALUATOR_LABEL}=1'})
        networks = client.networks.list(filters={'label': f'{EVALUATOR_LABEL}=1'})
    except docker.errors.DockerException as e:
        logger.warning(f"Evaluator cleanup skipped, Docker unavailable: {e}")
        return removed

    for container in containers:
        if not _is_expired(container.labels, now):
            continue
        try:
            container.remove(force=True)
            removed['containers'] += 1
        except docker.errors.APIError as e:
            logger.warning(f"Failed to remove leftover container {container.name}: {e}")

    for network in networks:
        if not _is_expired(network.attrs.get('Labels') or {}, now):
            continue
        try:
            network.remove()
            removed['networks'] += 1
        except docker.errors.APIError as e:
            logger.warning(f"Failed to remove leftover network {network.name}: {e}")

    return removed

def _is_expired(labels, now):
    try:
        return float(labels[EXPIRES_LABEL]) < now
    except (KeyError, TypeError, ValueError):
        return False
