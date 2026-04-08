from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from inspection_utils.config import load_yaml, save_yaml


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def safe_recipe_name(value: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in {'-', '_', '.'} else '_' for ch in value.strip())
    return cleaned or 'recipe'


@dataclass(slots=True)
class RecipeAtomicWriter:
    """Persist recipe and activation artifacts using atomic file replacement."""

    def save_yaml_atomic(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile('w', encoding='utf-8', delete=False, dir=str(path.parent), suffix='.tmp') as tmp:
            temp_path = Path(tmp.name)
            save_yaml(temp_path, data)
        os.replace(temp_path, path)

    def write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile('w', encoding='utf-8', delete=False, dir=str(path.parent), suffix='.tmp') as tmp:
            temp_path = Path(tmp.name)
            tmp.write(json.dumps(payload, ensure_ascii=False, indent=2))
        os.replace(temp_path, path)


@dataclass(slots=True)
class RecipeRevisionArchive:
    revisions_root: Path
    writer: RecipeAtomicWriter

    def write_snapshot(self, recipe_id: str, recipe: dict[str, Any], *, reason: str) -> None:
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        path = self.revisions_root / f'{timestamp}-{safe_recipe_name(recipe_id)}-{reason}.yaml'
        self.writer.save_yaml_atomic(path, recipe)

    def list_history(self, *, recipe_id: str = '') -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.revisions_root.glob('*.yaml'), reverse=True):
            name = path.stem
            if recipe_id and f'-{safe_recipe_name(recipe_id)}-' not in name:
                continue
            parts = name.split('-')
            reason = parts[-1] if parts else ''
            timestamp = '-'.join(parts[:2]) if len(parts) >= 2 else ''
            items.append({'file': path.name, 'reason': reason, 'timestamp': timestamp, 'path': str(path)})
        return items


class RecipeRepository:
    """Own recipe snapshot persistence and HMI profile projection."""

    def __init__(self, *, source_root: Path, config_root: Path, default_recipe_path: Path, writer: RecipeAtomicWriter) -> None:
        self.source_root = source_root
        self.config_root = config_root
        self.default_recipe_path = default_recipe_path
        self.writer = writer

    def seed_runtime_recipes(self) -> None:
        if not self.source_root.exists() or self.source_root == self.config_root:
            return
        for source_path in sorted(self.source_root.glob('*.yaml')):
            target_path = self.config_root / source_path.name
            if target_path.exists():
                continue
            try:
                shutil.copy2(source_path, target_path)
            except Exception:
                continue

    def list_recipe_paths(self) -> list[Path]:
        paths = sorted(self.config_root.glob('*.yaml'))
        unique: dict[str, Path] = {}
        for path in paths:
            unique[path.name] = path
        return list(unique.values())

    def load_all(self) -> list[dict[str, Any]]:
        recipes: list[dict[str, Any]] = []
        for path in self.list_recipe_paths():
            try:
                payload = load_yaml(path)
                if isinstance(payload, dict) and payload:
                    payload.setdefault('_path', str(path))
                    recipes.append(payload)
            except Exception:
                continue
        return recipes

    def load_by_id(self, recipe_id: str) -> dict[str, Any] | None:
        for recipe in self.load_all():
            if str(recipe.get('recipe_id', '')) == recipe_id:
                return recipe
        return None

    def current_default(self) -> dict[str, Any]:
        try:
            return load_yaml(self.default_recipe_path)
        except Exception:
            return {}

    def to_hmi_profile(self, recipe: dict[str, Any], *, active_recipe_id: str = '') -> dict[str, Any]:
        metadata = recipe.get('metadata', {}) if isinstance(recipe.get('metadata', {}), dict) else {}
        hmi = metadata.get('hmi_profile', {}) if isinstance(metadata.get('hmi_profile', {}), dict) else {}
        color_roi = (((recipe.get('vision', {}) or {}).get('color', {}) or {}).get('roi', {}) or {})
        qr_roi = (((recipe.get('vision', {}) or {}).get('qr', {}) or {}).get('roi', {}) or {})
        recipe_id = str(recipe.get('recipe_id', ''))
        sort_rules = hmi.get('sort_rules', []) if isinstance(hmi.get('sort_rules', []), list) else []
        if not sort_rules:
            sort_rules = [
                {'condition': 'decision == OK', 'action': 'BOX_OK'},
                {'condition': 'decision != OK', 'action': 'BOX_NG'},
            ]
        return {
            'id': recipe_id,
            'name': str(hmi.get('name', metadata.get('display_name', recipe_id or '未命名配方'))),
            'version': str(recipe.get('version', '1.0.0')),
            'targetPart': str(hmi.get('target_part', metadata.get('target_part', '待检工件'))),
            'roi': [int(color_roi.get('x', 0)), int(color_roi.get('y', 0)), int(color_roi.get('w', 0)), int(color_roi.get('h', 0))],
            'qrRoi': [int(qr_roi.get('x', 0)), int(qr_roi.get('y', 0)), int(qr_roi.get('w', 0)), int(qr_roi.get('h', 0))],
            'thresholdsSummary': str(hmi.get('thresholds_summary', metadata.get('notes', '规则检测阈值'))),
            'sortRules': [
                {'condition': str(item.get('condition', '')), 'action': str(item.get('action', ''))}
                for item in sort_rules if isinstance(item, dict)
            ],
            'enabled': recipe_id == active_recipe_id,
            'updatedAt': str(metadata.get('updated_at', '')),
            'updatedBy': str(metadata.get('author', 'operator')),
            'changeNote': str(hmi.get('change_note', metadata.get('notes', ''))),
        }

    def save_from_hmi(self, profile: dict[str, Any]) -> dict[str, Any]:
        recipe_id = str(profile.get('id', '')).strip() or 'recipe-generated'
        existing = self.load_by_id(recipe_id) or self.current_default() or {}
        recipe = dict(existing)
        recipe['recipe_id'] = recipe_id
        recipe['version'] = str(profile.get('version', recipe.get('version', '1.0.0')))
        metadata = recipe.setdefault('metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}
            recipe['metadata'] = metadata
        metadata['author'] = str(profile.get('updatedBy', metadata.get('author', 'operator')))
        metadata['display_name'] = str(profile.get('name', metadata.get('display_name', recipe_id)))
        metadata['target_part'] = str(profile.get('targetPart', metadata.get('target_part', '待检工件')))
        metadata['notes'] = str(profile.get('changeNote', metadata.get('notes', '')))
        metadata['updated_at'] = str(profile.get('updatedAt', '')).strip() or utc_now()
        metadata['hmi_profile'] = {
            'name': str(profile.get('name', metadata.get('display_name', recipe_id))),
            'target_part': str(profile.get('targetPart', metadata.get('target_part', '待检工件'))),
            'thresholds_summary': str(profile.get('thresholdsSummary', metadata.get('notes', ''))),
            'sort_rules': [
                {'condition': str(item.get('condition', '')), 'action': str(item.get('action', ''))}
                for item in (profile.get('sortRules', []) or []) if isinstance(item, dict)
            ],
            'change_note': str(profile.get('changeNote', metadata.get('notes', ''))),
        }
        vision = recipe.setdefault('vision', {})
        if not isinstance(vision, dict):
            vision = {}
            recipe['vision'] = vision
        color = vision.setdefault('color', {})
        if not isinstance(color, dict):
            color = {}
            vision['color'] = color
        qr = vision.setdefault('qr', {})
        if not isinstance(qr, dict):
            qr = {}
            vision['qr'] = qr
        color.setdefault('enabled', True)
        qr.setdefault('enabled', False)
        roi = list(profile.get('roi', []))
        qr_roi = list(profile.get('qrRoi', []))
        color['roi'] = {
            'x': int(roi[0]) if len(roi) > 0 else 0,
            'y': int(roi[1]) if len(roi) > 1 else 0,
            'w': int(roi[2]) if len(roi) > 2 else 0,
            'h': int(roi[3]) if len(roi) > 3 else 0,
        }
        qr['roi'] = {
            'x': int(qr_roi[0]) if len(qr_roi) > 0 else 0,
            'y': int(qr_roi[1]) if len(qr_roi) > 1 else 0,
            'w': int(qr_roi[2]) if len(qr_roi) > 2 else 0,
            'h': int(qr_roi[3]) if len(qr_roi) > 3 else 0,
        }
        target_path = self.config_root / f'{safe_recipe_name(recipe_id)}.yaml'
        recipe['_path'] = str(target_path)
        self.writer.save_yaml_atomic(target_path, {key: value for key, value in recipe.items() if key != '_path'})
        return recipe


class RecipeActivationService:
    """Own recipe activation lifecycle and activation receipt persistence."""

    def __init__(self, *, repository: RecipeRepository, archive: RecipeRevisionArchive, writer: RecipeAtomicWriter, activations_root: Path, current_root: Path) -> None:
        self.repository = repository
        self.archive = archive
        self.writer = writer
        self.activations_root = activations_root
        self.current_root = current_root

    def config_generation(self, recipe: dict[str, Any]) -> str:
        import hashlib
        normalized = dict(recipe or {})
        normalized.pop('_path', None)
        payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def build_activation_receipt(
        self,
        *,
        recipe: dict[str, Any],
        recipe_id: str,
        operator: str,
        previous_recipe_id: str,
        activation_state: str = 'PENDING_START',
        applied_batch_id: str = '',
        applied_at: str = '',
        runtime_acknowledged: bool = False,
    ) -> dict[str, Any]:
        return {
            'activationId': f'act-{datetime.now().strftime("%Y%m%d%H%M%S")}-{safe_recipe_name(recipe_id)}',
            'activatedAt': utc_now(),
            'activatedBy': operator,
            'recipeId': recipe_id,
            'recipeVersion': str(recipe.get('version', '1.0.0')),
            'configGeneration': self.config_generation(recipe),
            'previousRecipeId': previous_recipe_id,
            'defaultRecipePath': str(self.repository.default_recipe_path),
            'activationMode': 'NEXT_RUN',
            'activationState': activation_state,
            'effectiveOn': 'next_start',
            'runtimeAcknowledged': bool(runtime_acknowledged),
            'appliedBatchId': str(applied_batch_id),
            'appliedAt': str(applied_at),
        }

    def activate(self, recipe_id: str, *, operator: str = 'hmi_operator') -> dict[str, Any]:
        recipe = self.repository.load_by_id(recipe_id)
        if not recipe:
            raise FileNotFoundError(f'recipe not found: {recipe_id}')
        previous = self.repository.current_default()
        previous_id = str(previous.get('recipe_id', '')) if isinstance(previous, dict) else ''
        cloned = dict(recipe)
        cloned.pop('_path', None)
        metadata = cloned.setdefault('metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}
            cloned['metadata'] = metadata
        metadata['activated_at'] = utc_now()
        metadata['activated_by'] = operator
        self.writer.save_yaml_atomic(self.repository.default_recipe_path, cloned)
        self.writer.save_yaml_atomic(self.current_root / 'active_recipe.yaml', cloned)
        self.archive.write_snapshot(recipe_id, cloned, reason='activate')
        receipt = self.build_activation_receipt(recipe=cloned, recipe_id=recipe_id, operator=operator, previous_recipe_id=previous_id)
        self.writer.write_json_atomic(self.activations_root / f'{receipt["activationId"]}.json', receipt)
        self.writer.write_json_atomic(self.current_root / 'last_activation.json', receipt)
        return receipt

    def current_activation(self) -> dict[str, Any]:
        path = self.current_root / 'last_activation.json'
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def preflight_start_request(self, *, recipe_id: str, batch_id: str) -> dict[str, Any]:
        current = self.current_activation()
        if not current:
            raise RuntimeError('activation receipt missing')
        requested_recipe_id = str(recipe_id or '').strip()
        if not requested_recipe_id:
            raise RuntimeError('requested recipe id missing')
        if str(current.get('recipeId', '')) != requested_recipe_id:
            raise RuntimeError('activation receipt recipe does not match requested recipe')
        recipe = self.repository.load_by_id(requested_recipe_id)
        if not recipe:
            raise FileNotFoundError(f'recipe not found: {requested_recipe_id}')
        default_recipe = self.repository.current_default()
        default_recipe_id = str(default_recipe.get('recipe_id', '')) if isinstance(default_recipe, dict) else ''
        if default_recipe_id != requested_recipe_id:
            raise RuntimeError('default recipe snapshot does not match requested recipe')
        expected_generation = self.config_generation(recipe)
        activation_generation = str(current.get('configGeneration', ''))
        if activation_generation and activation_generation != expected_generation:
            raise RuntimeError('activation generation does not match recipe snapshot')
        default_generation = self.config_generation(default_recipe) if isinstance(default_recipe, dict) and default_recipe else ''
        if default_generation and default_generation != expected_generation:
            raise RuntimeError('default recipe snapshot generation mismatch')
        activation_state = str(current.get('activationState', ''))
        if activation_state in {'START_BLOCKED'}:
            raise RuntimeError('activation is blocked until recipe selection is refreshed')
        return {
            'activation': dict(current),
            'recipeId': requested_recipe_id,
            'batchId': str(batch_id),
            'recipeVersion': str(recipe.get('version', current.get('recipeVersion', '1.0.0'))),
            'configGeneration': expected_generation,
        }

    def mark_activation_start_blocked(self, *, recipe_id: str, batch_id: str, reason: str) -> dict[str, Any]:
        current = self.current_activation()
        if not current:
            return {}
        updated = dict(current)
        updated['activationState'] = 'START_BLOCKED'
        updated['blockedAt'] = utc_now()
        updated['blockedReason'] = str(reason)
        updated['requestedRecipeId'] = str(recipe_id)
        updated['requestedBatchId'] = str(batch_id)
        activation_id = str(updated.get('activationId', '')).strip()
        if activation_id:
            self.writer.write_json_atomic(self.activations_root / f'{activation_id}.json', updated)
        self.writer.write_json_atomic(self.current_root / 'last_activation.json', updated)
        return updated

    def mark_activation_start_requested(self, *, recipe_id: str, batch_id: str) -> dict[str, Any]:
        current = self.current_activation()
        if not current:
            raise RuntimeError('activation receipt missing')
        recipe = self.repository.load_by_id(recipe_id)
        if not recipe:
            raise FileNotFoundError(f'recipe not found: {recipe_id}')
        updated = dict(current)
        updated['activationState'] = 'START_REQUESTED'
        updated['appliedBatchId'] = str(batch_id)
        updated['appliedAt'] = utc_now()
        updated['recipeVersion'] = str(recipe.get('version', updated.get('recipeVersion', '1.0.0')))
        updated['configGeneration'] = self.config_generation(recipe)
        activation_id = str(updated.get('activationId', '')).strip()
        if not activation_id:
            activation_id = f'act-{datetime.now().strftime("%Y%m%d%H%M%S")}-{safe_recipe_name(recipe_id)}'
            updated['activationId'] = activation_id
        self.writer.write_json_atomic(self.activations_root / f'{activation_id}.json', updated)
        self.writer.write_json_atomic(self.current_root / 'last_activation.json', updated)
        return updated

    def mark_runtime_acknowledged(self, *, recipe_id: str, observed_at: str = '', batch_id: str = '', recipe_version: str = '') -> dict[str, Any]:
        current = self.current_activation()
        if not current:
            return {}
        if str(current.get('recipeId', '')) != str(recipe_id):
            return dict(current)
        recipe = self.repository.load_by_id(str(recipe_id))
        updated = dict(current)
        updated['runtimeAcknowledged'] = True
        updated['runtimeAcknowledgedAt'] = str(observed_at or utc_now())
        if batch_id:
            updated['runtimeObservedBatchId'] = str(batch_id)
        if recipe is not None:
            updated['recipeVersion'] = str(recipe.get('version', updated.get('recipeVersion', '1.0.0')))
            updated['configGeneration'] = self.config_generation(recipe)
        elif recipe_version:
            updated['recipeVersion'] = str(recipe_version)
        updated['activationState'] = 'RUNTIME_ACKNOWLEDGED'
        activation_id = str(updated.get('activationId', '')).strip()
        if activation_id:
            self.writer.write_json_atomic(self.activations_root / f'{activation_id}.json', updated)
        self.writer.write_json_atomic(self.current_root / 'last_activation.json', updated)
        return updated

    def list_activation_history(self, *, recipe_id: str = '') -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.activations_root.glob('*.json'), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if recipe_id and str(payload.get('recipeId', '')) != recipe_id:
                continue
            items.append(payload)
        return items
