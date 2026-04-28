from __future__ import annotations

from pathlib import Path
from typing import Any

from inspection_utils.io_common import resolve_resource_path, resolve_runtime_path

from .recipe_components import (
    RecipeActivationService,
    RecipeAtomicWriter,
    RecipeRepository,
    RecipeRevisionArchive,
    utc_now,
)


class RecipeActivationError(RuntimeError):
    """Raised when recipe activation state cannot safely advance."""


class RecipeStore:
    """Compatibility facade around the split gateway recipe components.

    The public API intentionally stays stable for existing callers while the
    implementation delegates persistence, activation lifecycle, and revision
    archiving to narrower components.
    """

    def __init__(self, config_root: str | Path = 'config/recipes') -> None:
        raw_root = Path(config_root).expanduser()
        self.source_root = resolve_resource_path(config_root, package_name='inspection_hmi_gateway', start=__file__)
        self.config_root = raw_root if raw_root.is_absolute() else resolve_runtime_path(config_root, start=__file__)
        self.config_root.mkdir(parents=True, exist_ok=True)
        self.default_recipe_path = self.config_root / 'default_recipe.yaml'
        self.state_root = self.config_root / '.state'
        self.activations_root = self.state_root / 'activations'
        self.revisions_root = self.state_root / 'revisions'
        self.current_root = self.state_root / 'current'
        for path in (self.state_root, self.activations_root, self.revisions_root, self.current_root):
            path.mkdir(parents=True, exist_ok=True)

        self.writer = RecipeAtomicWriter()
        self.repository = RecipeRepository(
            source_root=self.source_root,
            config_root=self.config_root,
            default_recipe_path=self.default_recipe_path,
            writer=self.writer,
        )
        self.revision_archive = RecipeRevisionArchive(self.revisions_root, self.writer)
        self.activation_service = RecipeActivationService(
            repository=self.repository,
            archive=self.revision_archive,
            writer=self.writer,
            activations_root=self.activations_root,
            current_root=self.current_root,
        )
        self.repository.seed_runtime_recipes()

    def _config_generation(self, recipe: dict[str, Any]) -> str:
        return self.activation_service.config_generation(recipe)

    def _build_activation_receipt(
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
        return self.activation_service.build_activation_receipt(
            recipe=recipe,
            recipe_id=recipe_id,
            operator=operator,
            previous_recipe_id=previous_recipe_id,
            activation_state=activation_state,
            applied_batch_id=applied_batch_id,
            applied_at=applied_at,
            runtime_acknowledged=runtime_acknowledged,
        )

    def _seed_runtime_recipes(self) -> None:
        self.repository.seed_runtime_recipes()

    def list_recipe_paths(self) -> list[Path]:
        return self.repository.list_recipe_paths()

    def load_all(self) -> list[dict[str, Any]]:
        return self.repository.load_all()

    def load_by_id(self, recipe_id: str) -> dict[str, Any] | None:
        return self.repository.load_by_id(recipe_id)

    def current_default(self) -> dict[str, Any]:
        return self.repository.current_default()

    def to_hmi_profile(self, recipe: dict[str, Any], *, active_recipe_id: str = '') -> dict[str, Any]:
        return self.repository.to_hmi_profile(recipe, active_recipe_id=active_recipe_id)

    def save_from_hmi(self, profile: dict[str, Any]) -> dict[str, Any]:
        recipe = self.repository.save_from_hmi(profile)
        recipe_id = str(recipe.get('recipe_id', '')).strip()
        if recipe_id:
            self.revision_archive.write_snapshot(recipe_id, {key: value for key, value in recipe.items() if key != '_path'}, reason='save')
        return recipe

    def validate_activation_candidate(self, *, recipe_id: str, batch_id: str, operator: str) -> dict[str, Any]:
        """Validate a recipe activation candidate without committing it.

        Args:
            recipe_id: Target recipe identifier.
            batch_id: Synthetic or real batch id used for start-contract checks.
            operator: Actor that would own the activation on commit.

        Returns:
            Staged activation and validation metadata.

        Raises:
            RecipeActivationError: The requested candidate cannot be staged.

        Boundary behavior:
            This method is side-effect free. It is safe for dry-run validation
            and for pre-commit checks inside the switch-recipe action workflow.
        """
        try:
            return self.activation_service.validate_activation_candidate(recipe_id=recipe_id, batch_id=batch_id, operator=operator)
        except Exception as exc:
            raise RecipeActivationError(str(exc)) from exc

    def activate(self, recipe_id: str, *, operator: str = 'hmi_operator') -> dict[str, Any]:
        return self.activation_service.activate(recipe_id, operator=operator)

    def current_activation(self) -> dict[str, Any]:
        return self.activation_service.current_activation()

    def preflight_start_request(self, *, recipe_id: str, batch_id: str) -> dict[str, Any]:
        try:
            return self.activation_service.preflight_start_request(recipe_id=recipe_id, batch_id=batch_id)
        except RuntimeError as exc:
            raise RecipeActivationError(str(exc)) from exc

    def mark_activation_start_blocked(self, *, recipe_id: str, batch_id: str, reason: str) -> dict[str, Any]:
        return self.activation_service.mark_activation_start_blocked(recipe_id=recipe_id, batch_id=batch_id, reason=reason)

    def mark_activation_start_requested(self, *, recipe_id: str, batch_id: str) -> dict[str, Any]:
        return self.activation_service.mark_activation_start_requested(recipe_id=recipe_id, batch_id=batch_id)

    def mark_runtime_acknowledged(self, *, recipe_id: str, observed_at: str = '', batch_id: str = '', recipe_version: str = '') -> dict[str, Any]:
        return self.activation_service.mark_runtime_acknowledged(
            recipe_id=recipe_id,
            observed_at=observed_at,
            batch_id=batch_id,
            recipe_version=recipe_version,
        )

    def _write_revision_snapshot(self, recipe_id: str, recipe: dict[str, Any], *, reason: str) -> None:
        self.revision_archive.write_snapshot(recipe_id, recipe, reason=reason)

    def _save_yaml_atomic(self, path: Path, data: dict[str, Any]) -> None:
        self.writer.save_yaml_atomic(path, data)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        self.writer.write_json_atomic(path, payload)

    def list_activation_history(self, *, recipe_id: str = '') -> list[dict[str, Any]]:
        return self.activation_service.list_activation_history(recipe_id=recipe_id)

    def list_revision_history(self, *, recipe_id: str = '') -> list[dict[str, Any]]:
        return self.revision_archive.list_history(recipe_id=recipe_id)
