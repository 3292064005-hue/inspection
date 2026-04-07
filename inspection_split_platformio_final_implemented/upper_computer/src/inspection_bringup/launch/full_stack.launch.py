from __future__ import annotations

from inspection_bringup.sim_stack_common import build_simulated_stack

_DEPRECATION_NOTICE = ('[inspection_bringup] full_stack.launch.py keeps the historical demo entrypoint and runs the simulated station stack. Prefer sim_stack.launch.py for new automation.')
# Compatibility note: shared builder still owns log_root/recipe_root/frontend_dist/users_path defaults.


def generate_launch_description():
    return build_simulated_stack(deprecation_notice=_DEPRECATION_NOTICE)
